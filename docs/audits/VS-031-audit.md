# VS-031 audit: cancellation and returns

Independent, read-only audit. Auditor date: 2026-10-25. Tree audited: branch `vs-031-cancellation-and-returns` @ `e7fc30e` (clean), which is tree-identical to `main` @ `7649b7d` (PR #41, squash-merged 2026-10-24). No source, test, migration or status file was changed. Mutation experiments ran only on a scratch copy (`git archive HEAD`) outside the repo.

## 1. Verdict

**Yes, with test gaps to close.** Every cancel, return and cash-block behaviour I checked works on real PostgreSQL. All three "Done when" lines have tests that fail when their guard is broken. The money core holds: a paid line always refunds its whole remaining balance, an unpaid cash line never refunds, and two cancels of one paid line refund it once. 33 of 42 mutations went red. The gaps are in what the tests can see. Removing the customer-cancel ownership check leaves the 551 slice tests green, because the route's later `order_detail_read` returns 404 and rolls the foreign cancel back (A-01). Removing the cancel's status-history rows also leaves everything green, although both order reads show that history (A-02). The SRS §5.6 end-to-end test also shares a phone number with `test_physical_checkout_api.py`. In either run order, one of the two fails (A-03); CI passes only because they run in different shards. Close A-01 and A-02 before VS-036 and VS-043 build on cancelled lines. Fix A-03 before any new end-to-end test uses that phone for cash.

**Follow-up (2026-10-25, branch `test/vs031-audit-fixes`):** A-01 to A-05 are fixed with tests only; no new test exposed an application bug. Re-applying M01, M02, M03, M39, M40 and M43 on the scratch copy now turns each red. A-06 (Nit) stays open; Q-1 is pending the owner's decision.

## 2. Repo state

| Item | Finding |
|---|---|
| Current branch | `vs-031-cancellation-and-returns` @ `e7fc30ef`; local `main` was at `4a23f4c` (stale). After `git fetch`, `origin/main` is `7649b7d` "VS-031: cancellation and returns (#41)" |
| Uncommitted/untracked | None at the start (`git status --short` empty). Afterwards the only untracked file is this report |
| VS-031 on `main`? | Yes. PR #41 head `e7fc30e` was squash-merged as `7649b7d`; `git diff e7fc30e 7649b7d` is empty |
| Slice commits (branch, before squash) | `59905e6` migration, `d856d05` edges and use case, `862085c` integration/e2e tests, `0172691` race tests, `44d3ab4` / `b8bbd1a` docs and ADRs, `657e2e7` review fixes, `eb60421` ADR-043 d12 (no cash for a line priced 0), `e7fc30e` VS-030 smoke head fix |
| Prior commit touching the slice | `4a23f4c` (#40) adds must-resolve item 2 to the plan |
| Diff size | 66 files, +4236 / -144 against `4a23f4c` |

## 3. Command results

| Tool | Result | Notes |
|---|---|---|
| `ruff check .` | PASS | "All checks passed!" |
| `ruff format --check .` | PASS | 901 files already formatted |
| `mypy src tests` (strict) | PASS | 773 source files, no issues (8 s) |
| `pytest tests/unit` | PASS | 2167 passed (98.6 s); includes `test_deep_architecture.py` and `test_cash_lock_order.py` |
| Integration, slice files (`test_cancel_api`, `test_cancel_refusals`, `test_line_transition_api`, `test_admin_order_queue_api`, `test_customer_cancel_api`, `test_cash_self_cancel_window`, `test_mixed_cancel_refunds`) | PASS | 238 passed (295.7 s) |
| `tests/integration/ordering/test_physical_checkout_api.py` (changed by the slice) | PASS | 28 passed (30.7 s) |
| `tests/concurrency/test_cancel_races.py` + `test_cash_checkout_races.py` | PASS | 23 passed (153.5 s), including the 100-iteration cancel-versus-printing race in both parametrisations |
| `tests/e2e/test_vs031_cancellation.py` + `test_vs029_admin_fulfillment.py` + `tests/smoke/test_vs030_smoke.py` | PASS | 6 passed (20.5 s) |
| `test_physical_checkout_api.py` then `test_vs031_cancellation.py` in one process | **FAIL** | `test_a_refused_cash_delivery_is_cancelled_unrefunded_and_blocks_cash`: first cash checkout gets 422 `CASH_NOT_AVAILABLE` (A-03) |
| The same two files in reverse order | **FAIL** | `test_snapshots_survive_later_edits_to_the_address_and_the_product`: checkout 422, `KeyError: 'order'` (A-03) |
| Full suite (GitHub CI) | PASS | PR run `40106334184` on `e7fc30e`: lint, unit and all six test shards green (8 min 8 s). Push run `40108127956` on `main` @ `7649b7d`: success. Not run locally (machine memory) |
| `alembic heads` | PASS | Exactly one head: `595b7e6e2792` |
| upgrade → downgrade → upgrade (throwaway `postgres:16` testcontainer) | PASS | `head` (column `timestamp with time zone` + both partial indexes) → `downgrade 80e56abf0969` (column and indexes gone) → `head` (both re-created as `... WHERE ((payment_method = 'cash'::payment_method) AND (customer_cancelled_at IS NOT NULL))`) |
| Committed `docs/frontend-handoff/openapi.json` vs `app.openapi()` | PASS | Paths and components identical |

**Mutation results.** Target set: the six unit files on cancellation, line transitions, the cancel balance invariant, the cash lock order, fulfillment steps and the customer view, plus the seven integration files above, `test_vs031_cancellation.py` and (for lock mutations) `test_cancel_races.py`. Scratch baseline over the 19 target files: 728 passed, 1 failed. The failure is A-03's order dependence (`test_physical_checkout_api.py` ran first); every per-mutation run excluded that file. Each mutation ran against its own subset; survivors were re-run against the whole target set (551 tests, no checkout file).

| Mutation (scratch copy only) | Result |
|---|---|
| M04 no refund on a paid cancel | RED |
| M05 block if any reason blocks (subset → intersection) | RED (`test_the_block_is_the_same_whatever_the_cancel_order`) |
| M06 a cancel with no recorded reason blocks | RED |
| M07 a live line does not prevent the block | RED |
| M08 drop the cart lock before the block | RED (`test_cash_lock_order`) |
| M09 drop the phone lock before the block | RED (`test_cash_lock_order`) |
| M10 self-cancel window: drop the by-phone branch | RED |
| M11 window boundary `>` → `>=` | RED (`test_the_window_ends_exactly_24_hours_after_the_cancel[0]`) |
| M12 every cancel sets `customer_cancelled_at` | RED |
| M13 self-cancelled online orders count toward the cash limit | RED |
| M14 cash allowed with a line priced 0 | RED |
| M15 `shipped → cancelled` for any unpaid cash total | RED |
| M16 `returned → cancelled` on a paid line | RED |
| M18 cancellation refund includes zero-balance lines | RED |
| M19 drop the unfinished-physical guard on cancellation items | RED |
| M20 customer cancel also takes non-pending physical lines | RED |
| M21 skip the `order.cancelled` audit row | RED |
| M22 skip the `order_cancelled` notice | RED |
| M23 customer's refund `approved_by` = the customer | RED |
| M24 recompute from the pre-cancel line states | RED |
| M25 no `refund_integrity` alert on a refused cancel | RED |
| M26 drop the customer cancel rate limit | RED |
| M27 drop CSRF on the admin order cancel | RED |
| M28 forward writer accepts `-> cancelled` | RED (`test_the_forward_writer_never_cancels_a_line`) |
| M29 `cancel_reason` on a forward edge silently ignored | RED (`test_a_transition_needs_csrf_and_a_foreign_line_is_a_404`) |
| M30 cancel refund skips the Q-2 totals check | RED |
| M31 no newly-reached step notice | RED |
| M32 block reason prefers `no_show` over `refused` | RED |
| M33 cancel notice drops the new amount due | RED |
| M34 admin order cancel: a reason no line takes is dropped silently | RED |
| M37 customer note not stored | RED (audit `note` assertion) |
| M38 status recompute with no refund facts | RED |
| M42 `customer_cancelled_at` never set | RED |
| **M01 customer cancel: drop the ownership check** (`cancel_lines.py:64`) | **GREEN (survives, 551 passed)** |
| **M39 cancel writes no status history** (`ordering/public.py:326-339`) | **GREEN (survives)** |
| **M40 cancel history drops the note** | **GREEN (survives)** |
| **M02 cancel writer: drop the `fulfillment_status == from_status` predicate** (`orders.py:348`) | **GREEN (survives, 551 passed)** |
| **M03 cancel writer: drop the row-count check** (`ordering/public.py:322-323`) | **GREEN (survives, 551 passed)** |
| **M43 admin order cancel: drop the rate limit** (`admin_orders.py:369-372`) | **GREEN (survives)** |
| M17 admin order cancel: drop the `payment_required` pre-check | GREEN (551 passed). Mostly equivalent: `line_cancel` raises `payment_required` for any eligible line; only the `reason` differs when no line is eligible (A-06) |
| M35 lines not locked `FOR UPDATE` | GREEN. Equivalent: every line writer takes the `orders` row lock first (ADR-024 d9), so the races still serialise. Pre-existing VS-023b guard |
| M36 block computed for paid orders too | GREEN. Equivalent: an online order never blocks (`cash_block_reason`), and a paid cash order's live lines are all delivered or picked up, so none can be cancelled |

## 4. Requirement checklist

| Requirement | Status | Code | Test(s) |
|---|---|---|---|
| `POST /me/orders/{id}/cancel`: verified owner, CSRF, 10/hour, 404 on foreign or unknown order | DONE (code) / PARTIAL (test) | `ordering/api/cancel.py:53-111`; ownership `fulfillment/application/cancel_lines.py:64` | `test_customer_cancel_api.py::test_another_customers_order_is_a_404_and_unchanged`, `::test_csrf_and_a_verified_email_are_required`, `::test_an_overlong_reason_is_a_422_and_the_limit_is_ten_an_hour` (M26 red). The 404 test passes without the ownership check (M01, A-01) |
| `POST /admin/orders/{id}/cancel`: admin boundary, CSRF, shared transition limit | DONE (code) / PARTIAL (test) | `fulfillment/api/admin_orders.py:366-403` | `test_cancel_api.py::test_the_admin_cancel_sits_behind_the_admin_boundary_and_csrf` (M27 red). Rate limit untested (M43, A-05) |
| Transition endpoint gains the `returned`, no-show and cancel edges, with `cancel_reason` | DONE | `ordering/domain/line_transitions.py:38-61, 78-123`; `fulfillment/application/transition_line.py:44-54` | `test_line_transitions.py`, `test_cancel_api.py::test_available_actions_list_the_cancel_reasons`, `test_admin_order_queue_api.py` (M15, M16, M29 red) |
| Lock order: orders, lines by id, payments, refund, lines, cart, phone, status | DONE | `cancel_lines.py:105-154`; `ordering/infrastructure/orders.py:208-221`; `payments/application/services/refunds.py:98-122`; `fulfillment/infrastructure/delivery_side.py:128-144` | `test_cash_lock_order.py::test_the_cancel_locks_the_cart_then_the_phone_then_inserts_the_block` (M08, M09 red); race tests below |
| Customer cancel = `can_cancel` under the locks: every live physical line `pending`, cash or paid, else 409 with no change | DONE | `ordering/domain/cancellation.py:70-84`; `customer_view.py:65` | `test_customer_cancel_api.py::test_a_cancel_that_cannot_occur_is_a_409_and_changes_nothing` (6 cases, flag and route agree), `test_cancellation.py` (M20 red) |
| ADR-033 d4: admin-cancelled lines neither block nor count | DONE | `customer_view.py:65` | `test_a_line_the_admin_already_cancelled_is_ignored` (one cancelled + one `pending` line) |
| Admin order cancel covers `pending`, `in_production`, `ready_to_ship`, `ready_for_pickup`; reasons per state | DONE | `cancellation.py:87-114` | `test_an_admin_cancel_leaves_stl_and_later_lines_alone`, `test_an_admin_cancel_that_cannot_occur_is_a_409_and_changes_nothing` (M34 red) |
| BR-148: admin cancel on `pending_payment` → 409 | DONE | `cancellation.py:100-101`; also `line_transitions.py:104-105` | `test_cancel_api.py` refusal params; `test_cancellation.py`. Pre-check partly redundant (M17, A-06) |
| Paid cancel: one pending `cancellation` refund for each line's whole remaining balance, none at 0; nothing cancelled if the refund cannot be created | DONE | `payments/domain/refunds.py:254-262`; `services/refunds.py:200-228`; `cancel_lines.py:116-125` | `test_an_admin_cancel_of_a_paid_line_refunds_its_whole_balance`, `test_cancel_balance_invariant.py`, `test_cancel_refusals.py` (all three routes) (M04, M18, M19, M25, M30 red) |
| Unpaid cash line never refunded (BR-149); refund item on a cancelled cash line → 422 | DONE | `cancel_lines.py:116` | `test_an_unpaid_cash_order_is_cancelled_with_no_refund`, `test_a_returned_cash_line_is_cancelled_with_no_refund`, `test_a_refund_item_on_a_cancelled_line_of_a_paid_cash_order_is_a_422` |
| `$0` unpaid cash line `shipped → cancelled` (`other`) | DONE | `line_transitions.py:82-83` | `test_a_shipped_zero_cash_line_is_cancelled_without_a_return` (M15 red) |
| `returned → shipped \| in_production`; `refunded` via the refund endpoint; `cancelled` on unpaid cash only | DONE | `line_transitions.py:43, 84-85` | `test_a_returned_line_is_reshipped_or_reprinted`, `test_a_returned_paid_line_is_never_cancelled_and_is_refunded_instead` (M16 red) |
| STL lines never cancelled | DONE | `line_transitions.py:94-103`; `ordering/public.py:414` | `test_an_admin_cancel_leaves_stl_and_later_lines_alone`, `test_an_stl_only_order_is_never_self_cancelled` |
| BR-144 cash block: all lines cancelled, every recorded reason `refused`/`no_show`, ≥ 1; online never; cancel order irrelevant | DONE | `cancellation.py:126-140`; `cancel_lines.py:141-144` | `test_a_whole_cash_order_refused_or_not_collected_blocks_cash`, `test_the_block_is_the_same_whatever_the_cancel_order`, `test_an_other_cancel_of_a_whole_cash_order_never_blocks`, `test_a_customer_cancel_after_an_admin_refusal_completes_the_block`, unit block-rule tests (M05-M07, M32 red) |
| Partly refused cash order: handover records the rest, no block; refusal leaving only `$0` lines ends `cancelled` without handover | DONE | `cancel_lines.py:141` | `test_a_partly_refused_cash_order_hands_over_the_rest_and_never_blocks`, `test_a_refusal_that_leaves_only_zero_lines_ends_cancelled_without_a_handover` |
| Cancel leaving a cash order live sends `order_cancelled` with the new amount due | DONE | `cancel_lines.py:209-221` | `test_a_partly_refused_cash_order_hands_over_the_rest_and_never_blocks` (`amount_due_cents == 1000`) (M33 red) |
| One notice per order per visible step (VS-029 note); re-ship announces `shipped` | DONE | `ordering/domain/fulfillment_steps.py:44-55`; `cancel_lines.py:222-231` | `test_a_cancel_that_leaves_the_rest_at_a_step_announces_it_once`, `test_step_newly_reached` (M31 red). Caveat: the re-ship test seeds `shipped` with no earlier notice, so it proves one notice on re-ship, not a second one |
| Queue keeps a cancelled paid order (`orders.cancelled_at` untouched) | DONE | `ordering/public.py:310-338` sets no `cancelled_at` | `test_admin_order_queue_api.py` (existing predicate tests) |
| One `order.cancelled` audit row per request, no phone or hash | DONE | `cancel_lines.py:157-193` | `test_a_paid_physical_order_is_cancelled_and_refunded_in_full` (M21 red) |
| FR-08: every transition records actor, prior state, new state, note | **PARTIAL** | `ordering/public.py:326-339` | **No test asserts the cancel's history rows** (M39, M40 survive, A-02) |
| Must-resolve 1 (ADR-038 d23): self-cancelled cash order counts 24 h, by customer and phone | DONE | migration `595b7e6e2792`; `ordering/infrastructure/cash.py:48-60`; `orders.py:369-375` | `test_cash_self_cancel_window.py` (place, cancel, probe; -1 s / 0 / +1 s; admin and online cancels do not count) (M10-M13, M42 red) |
| Must-resolve 2 (ADR-043 d1): no paid line left cancelled partly covered; chargeback stays satisfiable | DONE | `payments/domain/refunds.py:254-262` | `test_a_chargeback_for_the_whole_payment_after_a_cancel_is_satisfiable`, `test_a_physical_only_order_charged_back_after_a_cancel_needs_no_items`, `test_cancel_balance_invariant.py` |
| ADR-043 d12: cash refused for a cart with a line priced 0 | DONE | `ordering/domain/cash.py:41-42` | `test_a_cart_with_a_free_physical_line_is_refused_cash_but_can_pay_online` (M14 red) |

### Plan test list and "Done when" → tests

| Case | Test |
|---|---|
| **Done when 1:** SRS §5.6 end-to-end | `tests/e2e/test_vs031_cancellation.py::test_srs_5_6_a_mixed_order_partly_refunded_by_cancelling_its_physical_line` (pass alone; order-dependent, A-03) |
| **Done when 2:** cancel vs start printing, one winner, no deadlock, ×100, incl. printing on the last-checked line | `test_cancel_races.py::test_a_customer_cancel_racing_start_printing_has_exactly_one_winner[one_line, printing_on_the_last_line]` (`ITERATIONS = 100`, alternating queue order) |
| **Done when 3:** unpaid cash never refunded; only a whole-order refusal/no-show blocks, whatever the order | block-rule tests above; M04-M07 red |
| Handover racing an admin cancel on another line | `test_a_handover_racing_a_cancel_of_another_line_serialises_without_deadlock[True, False]` |
| Handover on an all-cancelled order → 409 | `test_a_refusal_that_leaves_only_zero_lines_ends_cancelled_without_a_handover` (`no_live_line`) |
| Concurrent cancels of the last two lines: `cancelled`, out of cash-due, not counted; one block for `refused` | `test_two_cancels_of_the_last_two_lines_leave_one_status_and_at_most_one_block[other, refused]` |
| Illegal edges: `returned → cancelled` paid; `returned → refunded` unpaid cash; `no_show` from `returned` / `ready_to_ship` | `test_a_returned_paid_line_is_never_cancelled_and_is_refunded_instead`; `test_a_returned_cash_line_is_cancelled_with_no_refund`; `test_no_show_is_refused_outside_pickup` (unit) and `test_an_admin_cancel_that_cannot_occur...` (`ready_to_ship` over HTTP) |
| `ready_for_pickup → cancelled`: cash blocks; online refunds, never blocks | `test_a_whole_cash_order_refused_or_not_collected_blocks_cash`, `test_a_pickup_no_show_on_an_online_order_refunds_and_never_blocks` |
| Self-cancel on `pending_payment` online and STL-only → 409, `can_cancel` false | `test_a_cancel_that_cannot_occur_is_a_409_and_changes_nothing[unpaid_online, pending_payment]`, `test_an_stl_only_order_is_never_self_cancelled` |
| Self-cancel on a paid mixed order | `test_a_paid_mixed_order_cancels_only_its_physical_line` |
| Cash refusal end to end, then other account with the same phone → online only | `test_a_refused_cash_delivery_is_cancelled_unrefunded_and_blocks_cash` (the same customer's next checkout is not exercised here; the block's user match is VS-028/VS-029 tested) |
| Mixed orders: cancel then STL refund; STL refund then started line cancelled; `returned → refunded` beside delivered STL; manual refund at exact remaining and +1 ¢; partial STL then full cancel; failed cancellation refund stays owed | `test_mixed_cancel_refunds.py` (one test each) |
| STL refund racing the physical cancel | `test_an_stl_refund_racing_the_physical_lines_cancellation_both_commit[True, False]` |
| Goodwill refund then self-cancel / admin cancel → exact remaining | `test_a_goodwill_refund_then_a_self_cancel_refunds_exactly_the_rest`; admin path in `test_mixed_cancel_refunds.py::_cancel_after_goodwill` |
| Self-cancel paid physical-only → `cancelled`, refund pending | `test_a_paid_physical_order_is_cancelled_and_refunded_in_full` (refund row `pending`; the admin queue listing is asserted in the §5.6 e2e) |
| Same-customer cash checkout on another phone racing a blocking cancel | `test_a_checkout_on_another_phone_racing_a_blocking_cancel_never_slips_past_it[True, False]` |
| FR-09 concurrency: two cancels of one paid line, one refund | `test_two_cancels_of_one_paid_line_refund_it_exactly_once[transition, order_cancel, customer]` |
| FR-09 failure: cancellation and refund atomic | `test_a_failing_refund_rolls_the_whole_cancel_back`, `test_cancel_refusals.py` |

## 5. Definition of Done

| Checkbox | Met? | Evidence |
|---|---|---|
| Migration reviewed, reversible, one head | Met | Cycle above; single head `595b7e6e2792`; CI ran the per-step down/up test. The plan said "Model / migration: None"; the migration comes from must-resolve 1 (ADR-038 d23) and the status line names it |
| Rules in owning context; ports only | Met | Rules are pure domain (`cancellation.py`, `line_transitions.py`, `cash.py`, `payments/domain/refunds.py`); `test_deep_architecture.py` passes. Ordering's customer route imports `app.fulfillment.public` while Fulfillment imports `app.ordering.public`: a two-way dependency between contexts, accepted in ADR-043 d2 |
| Auth, verified email, ownership, admin boundary, CSRF, rate limits | Met (code) / Partly (tests) | All present. The ownership check (A-01) and the admin cancel's rate limit (A-05) are not guarded by any test |
| Money in cents; UTC; server status | Met | `cancellation_items` integer cents; `datetime.now(UTC)` at both routes; status recomputed from fresh refund facts (M24, M38 red) |
| Side effects in the same transaction | Met | Refund, lines, block, history, audit, outbox and notification share the route session; `test_a_failing_refund_rolls_the_whole_cancel_back`. The integrity alert is written in its own transaction after the refusal, by design (ADR-043 d1) |
| Background jobs | n/a | None new; emails go through the existing outbox |
| Unit + PG integration + API/IDOR + a concurrency test per known race | Partly | Every race in the plan has a test. The race tests use a held `orders` lock and count waiters in `pg_stat_activity` instead of `meet_or_fail`. They fail if the racers never queue, so overlap is proven. The IDOR test is weak (A-01) and the history is untested (A-02) |
| Each "Done when" covered; CI green | Met | See section 4; CI run `40106334184` (PR) and `40108127956` (`main`) green |
| Docs and OpenAPI; Status Done | Met | `docs/cancellation.md`, ADR-043, ADR-038 d23, SRS/BR amendments, notification contract and api-endpoints updated; committed OpenAPI equals the generated one; plan Status Done; CLAUDE.md "Next up: VS-036" correct |
| Glossary naming | Met | `cancel_reason`, `customer_cancelled_at`, `Refund` of kind `cancellation`, `order.cancelled`; no synonyms |

## 6. Findings

| ID | Sev | Location | What is wrong | Why it matters | Suggested fix (not applied) | Scope |
|---|---|---|---|---|---|---|
| A-01 | Major | `fulfillment/application/cancel_lines.py:64`; `tests/integration/ordering/test_customer_cancel_api.py::test_another_customers_order_is_a_404_and_unchanged` | Removing the ownership check (M01) leaves all 551 slice tests green. The foreign cancel then runs in full (refund, lines, audit, outbox). `order_detail_read` raises 404 afterwards, and the unit of work rolls it back, so the IDOR test still sees 404 and an unchanged order | The one guard that stops a customer cancelling and refunding someone else's order is untested. Any refactor of the response (e.g. returning the use case's outcome) turns this into a live IDOR with no test failing. An integrity alert raised on the way is written in its own transaction and survives the rollback | Test `app.fulfillment.public.cancel_order_by_customer` directly with another user's id: expect `LineNotFoundError`, and no refund, history or audit row. Optionally also check ownership in the lock (`lock_owned_order`, as the VS-024 retry does) | VS-031. **Fixed** (tests only): `test_customer_cancel_api.py::test_the_use_case_refuses_another_customers_order_by_itself`; M01 now red |
| A-02 | Major | `ordering/public.py:326-339`; all cancel tests | Dropping the cancel's status-history rows (M39), or their note (M40), leaves every test green. No test reads `order_status_history` after a successful cancel | FR-08 requires every transition to record actor, prior state, new state and note. Both the customer's and the administrator's `OrderDetail.status_history` show these rows, so a regression silently erases cancellations from both timelines. ADR-043 d11 says the customer's reason "is kept in the status history" | In `test_a_paid_physical_order_is_cancelled_and_refunded_in_full` and one admin cancel test, assert `status_history` has `pending → cancelled` per line, with the actor and the trimmed note | VS-031. **Fixed** (tests only): history rows, actor and note asserted for the customer and the admin cancel (`cancel_support.cancel_history`), plus the `status_history` each route returns; M39 and M40 now red |
| A-03 | Minor | `tests/e2e/test_vs031_cancellation.py:43` (`PHONE = "71 123 456"`); `tests/integration/ordering/test_physical_checkout_api.py:729` (`+96171123456`) | Both use the same phone for cash checkouts. The e2e test leaves an active cash block on it; the checkout tests leave open cash orders on it. **Demonstrated:** each order of the two files fails one test (section 3) | CI is green only because they run in different shards. Any reshard, `-k` selection, local combined run, or new later e2e test paying cash with this phone fails spuriously; the next one is likely VS-036 | Use `random_phone()` for the e2e order (passing the same value to the second account's address), or clear the block in teardown | VS-031 (tests). **Fixed**: the VS-031 e2e, `test_physical_checkout_api.py` and the VS-028 / VS-029 e2e tests (which typed the same number) now use `random_phone()`; both run orders pass. The address and cash-block validation tests keep the number: they place no order |
| A-04 | Minor | `ordering/infrastructure/orders.py:348-367`; `ordering/public.py:322-323` | The cancel writer's stale-state guard (`fulfillment_status == from_status` and the row-count check) is untested: M02 and M03 each survive all 551 tests | Unreachable through the locked use case today, so it costs nothing now. But `ordering.public.cancel_lines` is a published writer whose docstring promises "each line from the state it was decided on", and nothing proves it | A direct test: lock an order, pass a `LineCancel` whose `from_status` is stale, and expect `InvalidLineTransitionError` with nothing written | VS-031 (tests). **Fixed**: `test_cancel_refusals.py::test_the_cancel_writer_refuses_a_line_not_in_the_state_decided_on`; M02 and M03 now red |
| A-05 | Minor | `fulfillment/api/admin_orders.py:369-372` | The admin order cancel's rate limit is untested: removing it (M43) leaves the cancel suites green | ADR-043 d11 says the administrator's cancels share the transition endpoint's per-administrator limit. A dropped dependency would go unnoticed | Exhaust the shared `admin_stl_delivery` budget through the transition endpoint, then expect 429 on `POST /admin/orders/{id}/cancel` | VS-031. **Fixed**: `test_cancel_api.py::test_the_admin_cancel_shares_the_transition_rate_limit`; M43 now red |
| A-06 | Nit | `ordering/domain/cancellation.py:100-101` | The `payment_required` pre-check in `admin_cancels` is redundant whenever an eligible line exists (M17 survives). It only decides the `reason` for an unpaid online order with no eligible physical line (e.g. after the hold release): `payment_required` rather than `no_cancellable_line` | The documented precedence (BR-148 first) has no test | Add the admin-cancel case for a released (all-cancelled) unpaid online order expecting `payment_required` | VS-031 |

Also checked, no issue found: two cancels of one paid line create one refund (3 entry-point pairs); the cart and phone locks are taken before the block insert, and the insert is idempotent on `order_id`. The self-cancel window boundary is exact at 24 h. A refused integrity check rolls back everything but the alert, and the alert's separate transaction does not block on the request's held locks (test passes on all three routes). OpenAPI declares 409/422/429 for both new routes. The cancel notice carries no phone or hash.

## 7. Open questions (SRS ambiguous)

- **Q-1 (pending decision):** SRS §22.1 (conventions table, "Idempotency") requires an `Idempotency-Key` on "checkout and refunds", and CLAUDE.md repeats it. ADR-043 d9 gives the cancel routes no key: a repeat finds the lines cancelled and returns 409, never a second refund (race tests confirm one refund). That is safe for money. But a client retrying after a lost 200 is told `ORDER_NOT_CANCELLABLE` for a cancel that succeeded. Is a cancel-created refund within the SRS rule, and is the 409-on-retry behaviour acceptable to the frontend? The ADR decided; the SRS wording was not amended.

## 8. How the commands were run

- Tools from the repo's `.venv` (Python 3.13.5). Docker Desktop was stopped at the start and was started for the testcontainers suites. Tests use their own `postgres:16` and Redis testcontainers; the compose stack was not touched.
- The full suite was not run locally (machine memory). CI's results for `e7fc30e` and the tree-identical `7649b7d` stand in for it.
- The migration cycle ran in a throwaway testcontainer: `alembic upgrade head`, `downgrade 80e56abf0969`, `upgrade head`, then `information_schema.columns` and `pg_indexes` read after each step.
- Mutations ran on a `git archive HEAD` copy in the session scratchpad, with `PYTHONPATH` pointed at its `src` and `.env.example` exported into the environment (as CI does). Each mutation was a single exact-string replacement, run with `pytest -x` on its subset and restored before the next. Afterwards `diff -rq --exclude=__pycache__` showed the copy identical to the repo. The repo checkout stayed clean throughout.
