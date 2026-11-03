# VS-040 audit: offer counter, accept, reject, withdraw

Independent, read-only audit. Auditor date: 2026-11-03. Tree audited: `3cdf05f` on branch `test/vs028-audit-fixes` (clean), whose tree is identical to `origin/main` @ `41e1ac5`. No source, test, migration or status file was changed. Probes and mutations ran only on a `git archive HEAD` copy in the session scratchpad.

**Status: every finding below is fixed on branch `fix/vs040-audit`, and Q-1 is decided.** Sections 1 to 5 record the tree as audited. Section 6 lists each fix.

## 1. Verdict

**Yes, with gaps in the tests.** No application bug is confirmed: every suite the slice owns passes on real PostgreSQL, CI's full suite is green on this tree, the migration goes down and comes back cleanly, and six probes of real behaviour found no money or state bug. The suite is a good regression net for most of the slice: of 80 mutations, 66 are caught, including every ownership filter, turn and deadline check, price cap, CSRF guard, audit write and CHECK. Of the 14 survivors, 13 are real test gaps and 1 is equivalent.

Three gaps are Major because the regression they would hide is user-visible or breaks a named rule:
- **Withdraw after a real administrator counter is never tested.** Dropping `remind_at=None` from `withdraw` leaves every test green, while a customer's withdrawal then answers 500 (A-06).
- **BR-040 / INV-10 is tested on customer accept only.** The kill switch could block counter, reject or withdraw unnoticed (A-07).
- **The reminder's row lock has no test.** Without it, two runs at once email the customer twice, against ADR-035 d3 (A-08).

Close these three before relying on this suite to protect later changes to the offer flow.

## 2. Repo state (Phase 1)

| Item | Finding |
|---|---|
| Branch / commit | `test/vs028-audit-fixes` @ `3cdf05f` |
| Relation to `main` | PR #59 squash-merged this branch as `41e1ac5`. `git rev-parse` gives the same tree for both (`5bd2fbc`), so CI's run on `41e1ac5` applies. The local `main` ref is stale at `c10f80e`; only `origin/main` was fetched |
| Uncommitted | None at the start. Afterwards the only untracked file is this report |
| VS-040 on `main`? | Yes: `4755b11` (#23), follow-up `bf0abd1` (#25, `expected_amount_cents`) |
| Later commits touching its files | `7003f8c` (#26, VS-041), `16ab43e` (#51, VS-045) |
| Migration | `8d2f6a1c3e57` (`remind_at`, two CHECKs, one index), recorded against the plan's "Model / migration: None" in the slice's Status line |

## 3. Command results (Phase 2)

| Command | Result | Notes |
|---|---|---|
| `ruff check .` | PASS | "All checks passed!" |
| `ruff format --check .` | PASS | 1021 files already formatted |
| `mypy src tests` (strict) | PASS | 870 source files, no issues |
| `pytest tests/unit` | PASS | 2499 passed, 1 min 54 s |
| `pytest tests/integration/negotiation` | PASS, one test deselected | 269 passed, 1 deselected, 2 min 36 s. The deselected test hangs locally: A-03 |
| `test_offer_action_races.py`, `test_offer_races.py` | PASS | 12 passed, 11 s |
| `tests/unit/negotiation`, `tests/smoke/test_vs040_smoke.py` | PASS | 228 passed, 3 s |
| Mutation baseline on the copy: the action, expiry and schema files, `test_offer_action_races.py`, `test_offer_checkout_races.py`, unit negotiation | PASS | 431 passed, 1 min 41 s |
| Wider baseline on the copy: the other offer suites (see below) | PASS, in one order | 199 passed, 1 deselected, 2 min 44 s. In another order 1 failed: A-15 |
| **GitHub Actions, full suite on `41e1ac5`** (run 41609443385) | PASS | **6766 passed, 1 skipped, 8 deselected**, across all seven test jobs. CI's result, not a local one |
| `alembic heads` | PASS | Exactly one head: `95ffee5fde3b` |
| upgrade → downgrade → upgrade on a throwaway `postgres:16` | PASS | See below |

The first local attempt, one process over all of these suites, hung at about test 265 and was stopped by hand; none of its results are counted. See A-03.

**Migration cycle.** Probed: the column `remind_at`, the index `ix_offers_remind_at`, and the CHECKs `ck_offers_remind_at_awaiting_customer` and `ck_offers_agreed_within_current`.

| Step | Version | Objects |
|---|---|---|
| `upgrade head` | `95ffee5fde3b` | all 4 present |
| `downgrade 4b7e2c9d1f30` (VS-040's parent) | `4b7e2c9d1f30` | all 4 gone |
| `upgrade 8d2f6a1c3e57` | `8d2f6a1c3e57` | all 4 back; the index is partial (`WHERE remind_at IS NOT NULL`) |
| `upgrade head` | `95ffee5fde3b` | all 4 present |

### Mutation results (Phase 4)

80 exact-string mutations, each asserted to match exactly once, applied one at a time and reverted, run with `-x` against that area's target tests. Totals: **66 red, 14 survived.** Every survivor was then re-run against wider tests, and all 14 stayed green:
- **Offer suites the first pass skipped** (12 survivors): `test_offer_settlement`, `test_offers_api`, `test_admin_offers_api`, `test_offer_checkout_e2e`, `test_offer_races`, `test_offer_checkout_races`, `test_account_deletion_races`, `test_offer_checkout_api`, `test_offer_checkout_schema`, `test_reports_api`, `test_account_deletion`, and the VS-039, VS-040 and VS-041 smoke files.
- **Migration suites** (M3 and M4): `test_model_migration_parity`, `test_migrations`, `test_migration_reversibility`, `test_deep_db_constraints_and_migrations`.

**Survivors**

| Mutation | Result | Outcome |
|---|---|---|
| D9 `withdraw` keeps `remind_at` | GREEN | Real gap: A-06. Under it a withdraw after a real counter answers 500 |
| S11 kill switch blocks a counter | GREEN | Real gap: A-07 |
| S12 kill switch blocks a reject | GREEN | Real gap: A-07 |
| S13 kill switch blocks a withdraw | GREEN | Real gap: A-07 |
| L5 reminder reads with no lock | GREEN | Real gap: A-08. Under it two runs send two emails |
| A5 customer accept loses the rate limit | GREEN | Real gap: A-09 |
| B3 reason body allows extra fields | GREEN | Real gap: A-10 |
| B4 reason has no length limit | GREEN | Real gap: A-10 |
| B5 reason allows control characters | GREEN | Real gap: A-10 |
| B6 counter message allows control characters | GREEN | Real gap: A-10 |
| J9 job swallows a lost connection | GREEN | Real gap: A-11 |
| L2 `SKIP LOCKED` becomes a blocking lock | GREEN | Real gap: A-12 |
| M3 migration creates no `ix_offers_remind_at` | GREEN | Real gap: A-13 |
| M4 migration has no `remind_at` backfill | GREEN | Equivalent in practice: VS-039 had no counter, so no `awaiting_customer` row could exist to backfill. Not a finding |

**Killed**

| Mutation | Killed by |
|---|---|
| L1 action lock: drop `FOR UPDATE` | `test_accept_racing_reject_one_wins` |
| L3 job lock: no lock at all | `test_a_last_second_answer_racing_the_expiry_job` |
| L4 clock read before the lock; D1 overdue offer not refused | `test_the_deadline_is_read_after_the_lock_is_taken` |
| O1 `lock()` ownership filter dropped | `test_another_customers_offer_is_404[counter]` |
| O2 `Responder.scope` always None | `test_a_customer_never_reaches_anothers_offer` |
| D2 `is_overdue` `>=` to `>`; D19 reminder ignores the deadline | `test_a_reminder_past_the_deadline_is_dropped_unsent` |
| D3 withdraw respects the turn | `test_withdraw_tells_administrators_and_sends_no_email` |
| D4 turn check removed | `test_out_of_turn_writes_nothing` |
| D5 closed or accepted check removed | `test_the_move_is_checked_before_the_amount_seen` |
| D6 no list-price cap | `test_accept_uses_todays_lowered_list_price` |
| D7 accept keeps `responds_by`; D8 accept keeps `remind_at` | `test_accept_freezes_the_amount_and_opens_the_checkout_window` |
| D10 customer floor dropped | `test_customer_counter_meets_the_floor_and_the_ceiling` |
| D11 admin ceiling dropped | `test_no_counter_above_todays_list_price` |
| D12 admin must meet the floor | `test_admin_counter_may_go_below_the_floor` |
| D13 `responds_by` not reset; D15 reminder at 50 % | `test_admin_counter_hands_the_turn_to_the_customer_and_arms_the_reminder` |
| D14 customer counter keeps the reminder | `test_customer_counter_hands_the_turn_back_and_clears_the_reminder` |
| D16 no cooldown armed | `test_reject_emails_the_customer_with_the_cooldown` |
| D17 zero price passes | `test_negotiable_needs_a_listed_priced_stl` |
| D18 checkout `>=` to `>`; J4 checkout audit skipped | `test_checkout_expiry_closes_once_and_tells_the_customer_in_app` |
| D20 `is_overdue` ignores the status | `test_only_awaiting_offers_can_expire` |
| Q1 admin `allowed_actions` computed as the customer | `test_admin_counter_passes_the_turn_and_emails_the_customer` |
| Q2 `MOVES` check removed | `test_a_party_cannot_make_the_others_move` |
| S1 service-level amount check removed; S2 both removed | `test_a_stale_accept_writes_nothing` |
| S3 ownership recheck removed | `test_accept_refuses_an_stl_owned_meanwhile` |
| S4 counter's product recheck removed | `test_counter_and_accept_recheck_the_product` |
| S5 audit skipped; S6 round not appended; S10 payload loses its details | `test_admin_counter_emails_and_notifies_the_customer` |
| S7 customer counter also emails | `test_customer_counter_tells_administrators_in_app_only` |
| S8 customer's own in-app note dropped; S9 accept email dropped | `test_accept_always_emails_the_customer` |
| S14 kill switch blocks an accept | `test_the_kill_switch_never_blocks_an_answer` |
| A1, A2, A3 customer CSRF; A13 unverified may answer | `test_guards` |
| A4, A6 counter and withdraw rate limit; A7 limit 61; A8 shared subject; A9 shared bucket | `test_actions_are_rate_limited_per_user` |
| A10, A11, A12 admin CSRF | `test_the_admin_boundary_on_every_action` |
| A14 410 translated to 409 | `test_an_expired_offer_is_410` |
| B1 accept allows extra fields; B2 accept amount not strict | `test_accept_requires_the_amount_seen` |
| B7 counter message not trimmed | `test_customer_counter_hands_the_turn_back_and_resets_the_deadline` |
| J1, J2, J3 reminder not cleared, not emailed, not in-app | `test_reminder_is_sent_once_per_turn` |
| J5 payment-in-flight exemption removed | `test_checkout_expiry_leaves_an_offer_with_a_payment_in_flight` |
| J6 reminder pass never runs; J10 `<` for `<=` | `test_the_reminder_is_sent_from_remind_at` |
| J7 checkout pass never runs; J11 `<` for `<=` | `test_the_checkout_window_closes_at_its_deadline` |
| J8 a failing row aborts the run | `test_one_failing_offer_never_stalls_the_other_passes` |
| J12 job not registered | `test_expire_offers_runs_every_five_minutes_and_at_startup` |
| M1 no `remind_at` CHECK | `test_only_the_customers_turn_carries_a_reminder` |
| M2 no agreed-within-current CHECK | `test_the_agreed_price_never_exceeds_the_amount_accepted` |

**Impact checks.** Two throwaway tests on the copy prove what A-06 and A-08 would hide. Both pass on clean code and fail under their mutation, so they would also kill it.

| Check | Clean code | Mutated |
|---|---|---|
| Submit, administrator counters, customer withdraws | 200, `withdrawn` | D9: **500** |
| Two `remind_offer` calls released together by a barrier | `[True, False]`, 1 email | L5: `[True, True]`, **2 emails** |

## 4. Requirement checklist (Phase 3)

| Requirement | Status | Code | Proving test |
|---|---|---|---|
| Customer counter, accept, withdraw routes | DONE | `api/offers.py:220,250,276` | `test_offer_actions_api.py` |
| Admin counter, accept, reject routes | DONE | `api/admin_offers.py:140,170,196` | `test_admin_offer_actions_api.py` |
| Each action locks the offer | DONE | `respond_to_offer.py:173`, `infrastructure/offers.py:219` | `test_accept_racing_reject_one_wins` (L1 red) |
| Time read after the lock | DONE | `respond_to_offer.py:176` | `test_the_deadline_is_read_after_the_lock_is_taken` (L4 red) |
| Out of turn: 409 `OFFER_NOT_YOUR_TURN`, writes nothing | DONE | `domain/offers.py:202` | `test_out_of_turn_is_409_and_writes_nothing`, `test_out_of_turn_is_409` (D4 red) |
| Deadline: 410 `OFFER_EXPIRED`, before the job has run | DONE | `domain/offers.py:185,202` | `test_the_deadline_holds_to_the_second_before_the_job_runs`, `test_the_deadline_holds_to_the_second` (D1, D2, A14 red) |
| Closed or accepted: 409 with `offer_status` | DONE | `domain/offers.py:202` | `test_a_closed_or_accepted_offer_is_409`, both files (D5 red) |
| Counter appends a round, switches the turn, resets `responds_by` | DONE | `domain/offers.py:239` | `test_customer_counter_hands_the_turn_back_and_resets_the_deadline`, `test_admin_counter_passes_the_turn_and_emails_the_customer` (D13, S6 red) |
| Counters unlimited (BR-082) | DONE | `domain/offers.py:239` | `test_a_whole_negotiation_is_kept_round_by_round` |
| Customer counter meets floor and ceiling; admin ceiling only (ADR-035 d1, d2) | DONE | `domain/offers.py:253-256` | `test_counter_amount_rules`, `test_admin_counter_has_a_ceiling_but_no_floor` (D10, D11, D12 red) |
| Accept freezes the amount, capped at list price | DONE | `domain/offers.py:290` | `test_accept_caps_the_agreed_amount_at_todays_list_price`, `test_admin_accept_caps_at_todays_list_price` (D6 red) |
| Accept names the amount seen, checked before the rechecks (ADR-035 d9) | DONE | `domain/offers.py:271`, `respond_to_offer.py:105` | `test_a_stale_accept_writes_nothing` (S1, S2 red), `test_accepting_from_a_stale_admin_page_is_409_and_writes_nothing` |
| Accept sets the checkout window and clears `responds_by` (BR-086, BR-087) | DONE | `domain/offers.py:298` | `test_accept_freezes_the_amount_and_opens_the_checkout_window` (D7 red), `test_an_accepted_offer_never_expires_from_inactivity`, `test_only_awaiting_offers_expire` |
| Reject starts the cooldown; 0 means none | DONE | `domain/offers.py:315` | `test_reject_arms_the_cooldown_and_a_resubmission_waits_for_it`, `test_with_a_zero_cooldown_the_customer_may_offer_again_at_once` (D16 red) |
| Withdraw from both awaiting states, whoever's turn | DONE | `domain/offers.py:323` | `test_withdraw_from_either_awaiting_state` (D3 red); the SRS diagram disagrees: A-02 |
| Withdraw clears a live reminder | PARTIAL | `domain/offers.py:323` | Works (probe P1). No test: A-06 |
| Counter and accept recheck the product; reject and withdraw always work | DONE | `respond_to_offer.py:181` | `test_counter_and_accept_recheck_the_product` (S4, D17 red), `test_reject_and_withdraw_work_on_a_hidden_product` |
| Accept rechecks ownership (FR-13 concurrency) | DONE | `respond_to_offer.py:108` | `test_accepting_an_stl_bought_meanwhile_is_409`, `test_an_accept_racing_a_cart_payment_ends_auto_closed` (S3 red) |
| Kill switch never blocks an answer (BR-040, INV-10) | PARTIAL | No check in `respond_to_offer.py` | Customer and admin accept share `accept_offer` (S14 red). Counter, reject, withdraw untested: A-07 |
| Accept racing reject: one wins | DONE | row lock | `test_accept_racing_reject_one_wins` |
| Other races: withdraw vs accept, double counter, answer vs job, overlapping checkout expiry | DONE | row lock, `SKIP LOCKED` | `test_withdraw_racing_admin_accept_one_wins`, `test_a_double_clicked_counter_counts_once`, `test_a_last_second_answer_racing_the_expiry_job` (L3 red), `test_overlapping_checkout_expiry_runs_close_once` |
| Two reminder runs at once send once (ADR-035 d3) | PARTIAL | `expire_offers.py:111` | Works (impact check). No test: A-08 |
| The job skips a locked row rather than waiting (ADR-035 d5) | PARTIAL | `infrastructure/offers.py:223` | No test: A-12 |
| `expire_offers` closes accepted offers past their window | DONE | `expire_offers.py:58`, `domain/offers.py:346` | `test_the_checkout_window_closes_at_its_deadline` (D18, J7, J11 red), `test_checkout_expiry_rerun_is_a_noop` |
| One failing offer never stalls the job | DONE | `public.py:177` | `test_one_failing_offer_never_stalls_the_other_passes` (J8 red) |
| A lost database connection still fails the run (ADR-035 d6) | PARTIAL | `public.py:189` | No test: A-11 |
| Emails: countered, accepted, rejected | DONE | `respond_to_offer.py:37-39` | `test_admin_counter_emails_and_notifies_the_customer`, `test_accept_always_emails_the_customer`, `test_reject_emails_the_customer_with_the_cooldown` (S7, S9 red) |
| "Expiring soon" at 75 %, once | DONE | `domain/offers.py:234`, `expire_offers.py:101` | `test_reminder_falls_at_three_quarters_of_the_turn`, `test_the_reminder_is_sent_from_remind_at`, `test_the_reminder_is_sent_once` (D15, J1, J2, J3, J6, J10 red) |
| Every round kept permanently (BR-091) | DONE | `infrastructure/offers.py:246` | `test_a_whole_negotiation_is_kept_round_by_round` |
| Verified email and CSRF on every action; admin boundary | DONE | `api/offers.py`, `api/admin_offers.py` | `test_guards`, `test_the_admin_boundary_on_every_action` (A1, A2, A3, A10, A11, A12, A13 red) |
| 60 actions per user per hour | PARTIAL | `api/offers.py:58,107` | `test_actions_are_rate_limited_per_user` covers counter and withdraw (A4, A6 to A9 red), not accept: A-09 |
| Bodies validated | PARTIAL | `api/offer_schemas.py:41,61` | Counter amounts and accept bodies are tested (B1, B2, B7 red). The `reason` body and control characters in `message` are not: A-10 |
| 404 on another customer's offer | DONE | `infrastructure/offers.py:215` | `test_another_customers_offer_is_404` (O1, O2 red) |
| FR-13 failure: a refused counter or accept leaves the turn unchanged | DONE | refusals precede writes | `test_out_of_turn_is_409_and_writes_nothing`, `test_a_stale_accept_writes_nothing` |
| FR-13 failure: a side effect failing mid-action rolls back | PARTIAL | one request transaction | Works (probe P3). No such test in the action suites: A-14 |
| Every transition follows SRS §20.6 | PARTIAL | `domain/offers.py` | One legal transition is not in the diagram: A-02 |

## 5. Definition of Done

| Item | Met? | Evidence |
|---|---|---|
| Migration reviewed, reversible, one head | Met | Section 3 |
| Rules in the owning context; ports only | Met | Rules sit in `negotiation/domain`; other contexts come through `adapters.py`. `test_deep_architecture.py` passes in the unit run |
| Auth, verified email, ownership, admin boundary, CSRF, rate limits | Met (code) | All guards present and all but one proven by mutation; the exception is accept's rate limit (A-09) |
| Money in cents, UTC, server computes prices and status | Met | `StrictInt` amounts (probe P4 refuses `true`, `"800"`, `900.0` and 2^63); timestamps are timestamptz |
| Audit, notification and outbox in one transaction | Met (code) | Probe P3 shows all of it rolling back together; no test keeps that: A-14 |
| Background jobs registered, idempotent, tested | Partly | J6, J7, J8, J12 red; the reruns are tested. Gaps: A-08, A-11, A-12 |
| Unit, PostgreSQL, API error and IDOR tests, and a race test per known race | Partly | Race tests use `meet_or_fail`. The reminder race has none: A-08 |
| Each "Done when" tested; `ruff`, `mypy`, `pytest` green in CI | Partly | Green in CI. "Every transition follows §20.6" is literally false for one arrow: A-02 |
| Docs and OpenAPI updated; Status Done | Partly | The plan says Done; `test_openapi_snapshot.py` passes. Doc mismatches: A-04, A-05 |

**Test strength.** No `caplog` or `configure_logging` in the slice's test files, so that known weakness does not apply. The slice makes no timing claims.

## 6. Findings

No application bug is confirmed. All three Major findings are regressions the suite would not catch; the code behaves correctly today. Findings A-01 to A-05 keep the IDs of this report's first, partial version.

| ID | Sev | Location | What is wrong | Impact | Fix (not applied) | Slice |
|---|---|---|---|---|---|---|
| A-06 | Major; **fixed** | `domain/offers.py:323`; `test_offer_transitions.py:218`; `test_offer_actions_api.py:180` | D9 survives. No test withdraws an offer that holds a reminder: the unit test sets `remind_at=None`, and `seed_offer` never sets one for the API test. The admin-counter-then-withdraw flow is never run end to end | Under D9 the row hits `ck_offers_remind_at_awaiting_customer` and the withdraw answers **500** (impact check). Every offer an administrator has countered would become impossible to withdraw, with CI green | Parametrise the unit test with a live `remind_at`, and add an API test: submit, admin counter, withdraw. The impact check kills D9 | VS-040 |
| A-07 | Major; **fixed** | `respond_to_offer.py:68,138,156`; `test_offer_actions_api.py:329` | S11, S12 and S13 survive. BR-040 and INV-10 say the kill switch never affects responding to or withdrawing an existing offer, but only accept is tested paused | A check added around a pause could trap customers in live offers or stop the administrator answering, unnoticed | Parametrise `test_the_kill_switch_never_blocks_an_answer` over every customer and admin action | VS-040 |
| A-08 | Major; **fixed** | `expire_offers.py:111`; `tests/concurrency/test_offer_action_races.py` | L5 survives. No test under `tests/concurrency` mentions reminders, though ADR-035 d3 promises two runs at once send once. Only sequential reruns are tested | Under L5, two runs send **two emails** (impact check). By reading, not reproduced: its `save_state` writes the whole row from a stale read, so it could also overwrite a concurrent answer | Add the barrier race from the impact check, plus a reminder racing a customer's accept | VS-040 |
| A-01 | Minor; **fixed** | `domain/offers.py:215`, `offer_queries.py` | `allowed_actions` ignores the product and ownership rechecks. Probe P2: on a hidden product it lists `counter`, `accept`, `withdraw`, and counter then answers `422 PRODUCT_NOT_PURCHASABLE`. On an owned STL it lists the same, and accept answers `409 PRODUCT_ALREADY_OWNED` | The field is described as "what the caller may do now", so a frontend offers buttons that always fail. `docs/offers.md` defines it by status alone, so the code matches that table | Compute it with the same rechecks, or change the field's description to say it reflects status and turn only | VS-040 |
| A-02 | Minor; **fixed** | SRS §20.6, `database-design.md` §17.6 | Neither diagram draws `awaiting_admin → withdrawn`, which the code allows and `test_withdraw_from_either_awaiting_state` requires. ADR-034 records the owner's decision, and FR-13 and `entities-and-business-rules.md` agree, but ADR-035 amended the diagrams for accept and not for this. Erasure's `accepted → withdrawn` (`domain/offers.py:334`) is not drawn either | The SRS is the authority and contradicts the built behaviour, and the slice's "Done when" cites it | Add the arrows to both diagrams | VS-040 (docs) |
| A-03 | Minor; **fixed** | `tests/integration/negotiation/test_offers_api.py:416` | `test_submission_is_rate_limited_per_user` opens a nested `client_for(main_app)` inside the `client` fixture. In multi-test runs on this Windows machine it hangs forever at the outer client's teardown, in the proactor's `close` (2 of 2 runs: the union run and the file alone; the stack came from `faulthandler_timeout`). Alone it passes (2 of 2) and it passes on CI | A local negotiation run stalls with no output, and it has to be noticed by hand. The VS-041 audit ran this suite locally without this hang, so the timing varies | Use one client at a time, as `as_customer` does in `test_admin_offer_actions_api.py` | VS-039 (test) |
| A-09 | Minor; **fixed** | `api/offers.py:249`; `test_offer_actions_api.py:367` | A5 survives. The limit test spends counter and withdraw only | Accept could lose its limit unnoticed (SEC-11) | Parametrise the limit test over all three routes | VS-040 |
| A-10 | Minor; **fixed** | `api/offer_schemas.py:48,61-68` | B3, B4, B5 and B6 survive. The `reason` body's `extra="forbid"`, length limit and control-character rule have no test, nor does the control-character rule on a counter's `message`. Probe P4 shows all four refuse today | Weakening them goes unnoticed. These strings are stored in rounds and shown to the other party | Add the bad bodies from probe P4 to the action tests, on withdraw and reject | VS-040 |
| A-11 | Minor; **fixed** | `negotiation/public.py:189` | J9 survives. ADR-035 d6 says a lost connection still fails the run, but no test raises one | The job could log every row as failed and report success during an outage | A test whose step raises `OSError` and an invalidated `DBAPIError`, asserting the run raises | VS-040 |
| A-12 | Minor; **fixed** | `infrastructure/offers.py:223` | L2 survives. Nothing holds a row lock while the job runs, so `SKIP LOCKED` could become a blocking lock | Correctness holds, because the job re-checks under the lock, but it could stall behind a held row | Hold a row's lock in one session, run the job, and assert it returns without touching that row | VS-040 |
| A-13 | Minor; **fixed** | `test_model_migration_parity.py`; migration `8d2f6a1c3e57` | M3 survives. The model declares `ix_offers_remind_at`, yet removing it from the migration is unnoticed: `offers` and `offer_rounds` are not in the parity test's table list (grep: no hit), and no schema test names the index | The reminder pass could lose its index, a slow query on a growing table, with no failing test | Add both tables to the parity list, or assert the index in `test_offer_schema.py` | VS-040 |
| A-14 | Minor; **fixed** | `tests/integration/negotiation/test_offer_actions_api.py`, `test_admin_offer_actions_api.py`, `tests/unit/negotiation/test_offer_actions.py` | FR-13's failure case has no test in these files (grep for rollback or forced failures: no hit). Probe P3 shows it works: counter, accept and withdraw with a failing notification write all answer 500 with the row and side effects unchanged | CLAUDE.md treats FR failure sections as required tests. No mutation was prepared for this one, so the evidence is the grep and the probe | Keep probe P3 as a test | VS-040 |
| A-04 | Nit; **fixed** | `api-endpoints.md:453,632,1004,1010` | The doc names `OfferWithdrawRequest` and `OfferRejectRequest`; the code and OpenAPI have one `OfferReasonRequest` (grep of `openapi.json`: 0 and 2 hits). Line 453 omits the `422` that probe P4 gets on withdraw; line 632 shares that schema | The handoff doc and the OpenAPI file disagree on names | Align the names and add `422` | VS-040 (docs) |
| A-05 | Nit; **fixed** | `entities-and-business-rules.md:891,937` | The offer lifecycle has `AUTO_CLOSED` only from `ACCEPTED`; SRS §20.6 says every live state (ADR-037) | A stale supporting document | Add the two awaiting arrows | VS-041 (docs) |
| A-15 | Nit; **fixed** | `test_offer_settlement.py:185` | `assert result["checkout_expired"] == 0` counts every offer in the shared database. Running `test_admin_offers_api.py` first makes `test_the_job_leaves_an_offer_whose_payment_is_in_flight` fail on clean code (reproduced). Alone (2 of 2), with its own file (20 passed), and in the default order it passes | Default file order hides it; a rename, `-k` selection or new test can make it fail spuriously | Assert on this offer's state only | VS-041 (test) |

### Fix status

Every test-gap fix was proven by re-applying the surviving mutation on a copy of the branch: each one that stayed green in the audit now goes red, in the test named here.

| ID | Fix | Mutation now killed by |
|---|---|---|
| A-06 | Unit test with a live reminder; new API flow: submit, admin counter, withdraw | D9: `test_withdraw_from_either_awaiting_state_whoever_has_the_turn`, `test_a_customer_withdraws_after_a_real_admin_counter` |
| A-07 | The kill-switch test covers all six answers, customer and administrator | S11, S13: `test_the_kill_switch_never_blocks_an_answer`; S12: `test_the_kill_switch_never_blocks_an_administrators_answer` |
| A-08 | Two new races: two reminder runs at once, and a reminder against an accept | L5: `test_two_reminder_runs_at_once_send_one_email` |
| A-09 | The limit test covers all three customer routes | A5: `test_actions_are_rate_limited_per_user[accept]` |
| A-10 | Bad reasons on withdraw and reject; control characters in a counter's message | B3, B4, B5: `test_a_bad_withdraw_reason_is_422_and_writes_nothing`; B6: `test_counter_amount_rules` |
| A-11 | A lost connection fails the run; a statement error on one row does not | J9: `test_a_lost_connection_fails_the_run` |
| A-12 | The job runs while a row's lock is held, on all three passes | L2: `test_the_job_skips_a_locked_offer_instead_of_waiting` |
| A-13 | `offers` and `offer_rounds` added to the parity list | M3: `test_models_match_the_migration` |
| A-14 | A failing notification (customer) and a failing email (administrator) each roll the action back | No mutation: `test_a_failing_side_effect_rolls_the_whole_action_back`, `test_a_failing_email_rolls_the_whole_answer_back` |
| A-01 | `allowed_moves` also takes the product and ownership. Counter and accept are hidden on an unlisted, unavailable or zero-priced product and on an owned STL. New mutations N1, N2, N3 are killed by `test_allowed_actions_never_list_a_move_the_rechecks_refuse` and `test_allowed_actions_never_list_what_the_rechecks_refuse` | |
| A-02 | SRS §20.6 and `database-design.md` §17.6 now draw `awaiting_admin → withdrawn`. Erasure's `accepted → withdrawn` stays undrawn: the fix covered only the arrow the owner named | |
| A-03 | The test opens one client at a time; `test_offers_api.py` runs in full with no hang | |
| A-04 | `api-endpoints.md` names one `OfferReasonRequest` and lists `422` on withdraw and reject | |
| A-05 | The offer lifecycle shows `AUTO_CLOSED` from both awaiting states | |
| A-15 | The test asserts its own offer's state, not the job's global count; it passes after `test_admin_offers_api.py` | |

**A counter on an owned STL is hidden, not refused.** Only accept rechecks ownership (ADR-035 d4), so the route still answers 200 there while `allowed_actions` leaves it out. `test_a_counter_on_an_owned_stl_is_hidden_but_not_refused` pins this. It is effectively unreachable, because VS-041's auto-close closes live offers in the payment's own transaction, and a counter cannot lead to a sale.

Also checked, no issue found: malformed bodies on every route (probe P4), the real admin-counter-then-withdraw flow (probe P1), rollback when a side effect fails (probe P3), audit rows carrying the actor, request id and IP hash with no free text (probe P6), and an accept racing a cart payment (`test_an_accept_racing_a_cart_payment_ends_auto_closed`).

## 7. Open questions

- **Q-1 (decided, owner 2026-11-03: no offer emails; their offers expire normally; [ADR-035](../adr/ADR-035-offer-negotiation.md) d10):** Should a deactivated customer keep receiving offer emails? Probe P5: an administrator's counter on an offer whose customer has `active=False` returns 200 and queues `offer_countered` plus an in-app notification. That customer cannot log in to answer, so the offer then runs to expiry. The specification does not say whether deactivation closes live offers or silences them. `PlatformOfferMailer` now writes no email for a deactivated, anonymised or deleted account. In-app notifications stay. Tests: `test_a_deactivated_customer_gets_no_offer_email`, `test_a_deactivated_customer_gets_the_reminder_in_app_only`, `test_a_deactivated_customers_offer_expires_normally`, `test_an_anonymised_or_deleted_account_gets_no_offer_email` (mutations N4 to N7 killed).

## 8. How the commands were run

- **Environment.** The project's `.venv`, with `.env.example` values exported for the scratch copy. The real `.env` was neither read nor changed. Tests use their own testcontainers.
- **Docker.** It was stopped at the start. Starting Docker Desktop also restarted the compose dev stack (`restart: unless-stopped`). At the owner's request the stack was then stopped with `docker compose down`, keeping the volumes `bekaa3d_pgdata` and `bekaa3d_clamav_defs`. It was not restarted.
- **The hang.** The first run was stopped by PID after its CPU time stayed flat and the database sat idle. Later runs used `-o faulthandler_timeout` and deselected the one test in A-03. Suites ran in separate processes, with output redirected to files so exit codes stayed real.
- **Probes.** P1 to P6 and the impact checks lived only on the scratch copy, which was confirmed to import its own `src`. They were removed afterwards.
- **Mutations.** The first run was stopped by the host for low memory during L2. At the owner's request it resumed in small foreground batches after the compose stack was stopped. Available memory held at about 3 GB throughout, up from about 2.5 GB just after the stop. The driver stopped itself below 1 GB and each batch refused to start below 1.5 GB; neither triggered.
- **Restoring the copy.** The driver reverted each mutation, and after each batch the copy was re-extracted from `git archive HEAD` and compared with the repo's `src` and `migrations`, ignoring line endings. All matched.
- **Results.** The driver and its result files (`mutate.py`, `logs/mutations.jsonl`, `logs/survivors.jsonl`) are in the session scratchpad.
