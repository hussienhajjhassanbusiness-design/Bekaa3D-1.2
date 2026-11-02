# VS-050 audit: manual payment provider

Independent, read-only audit. Auditor date: 2026-11-02. Tree audited: `origin/main` @ `d613470` (the local branch `fix/vs030-audit-findings` @ `b68bc1a` has an identical tree: `git diff b68bc1a origin/main` is empty). No source, test, migration or status file was changed. Mutation experiments and probes ran only on a scratch copy (`git archive origin/main`) outside the repo.

## 1. Verdict

**Yes.** VS-050 is a trustworthy base for later slices (VS-020's production use, VS-021's emails, a future VS-032). Every "Done when" line and every FR case the slice added has a test. All 48 mutations of the slice's guards were killed: database constraints, reference locking and uniqueness, the phone-to-call rules, the per-provider hold at every call site, the job's manual answer, the alerts and notices, the work-list filter and the any-time admin release. The races use `meet_or_fail` and provably overlap. I found no Critical or Major issue. One Minor behaviour gap: a `noop` confirm on an attempt that is already paid still writes the typed reference onto it (A-01), plus three nits. The open questions are design questions for the owner, not defects. **Update 2026-11-02:** A-01 to A-04 are fixed and Q-1 and Q-2 resolved on branch `fix/vs050-audit-findings` (§6, §7).

## 2. Repo state

| Item | Finding |
|---|---|
| Current branch | `fix/vs030-audit-findings` @ `b68bc1a`; its tree equals `origin/main` @ `d613470` (#56 merged it) |
| Uncommitted/untracked | None at the start (`git status --short` empty). Afterwards the only new file is this report |
| VS-050 on `main`? | Yes: squash commit `fbd5872` (#55), 86 files, +2323/−258 |
| Later commits touching VS-050 files | None. `d613470` (VS-030 audit fixes) touches refunds and chargebacks only |
| Earlier commits on the reused code | `13af56f`, `ef8609f` (VS-024 recovery and admin reads), `a873774` (VS-030 record-capture) |

## 3. Command results

| Tool | Result | Notes |
|---|---|---|
| `ruff check .` | PASS | "All checks passed!" |
| `ruff format --check .` | PASS | 1011 files already formatted |
| `mypy src tests` (strict) | PASS | 864 source files, no issues |
| `pytest tests/unit` | PASS | 2481 passed, 4 warnings, 93.8 s |
| Slice integration + contract batch (12 files, list in §8) | PASS | **236 passed**, 152.6 s |
| Slice concurrency batch (`test_manual_payment_races.py`, `test_payment_recovery_more_races.py`) | PASS | **122 passed**, 169.5 s |
| Full suite | PASS **(CI, not local)** | Run 41319121894 on `fbd5872` (the VS-050 merge): 6718 passed, 1 skipped. Run 41357694703 on `d613470` (audited tree): 2480 + 674 + 592 + 496 + 680 + 626 + 1176 = **6724 passed, 1 skipped, 8 deselected**, all 7 shards green |
| `alembic heads` | PASS | Exactly one head: **`941b40d285ce`** |
| upgrade → downgrade → upgrade (throwaway `postgres:16` testcontainer) | PASS | See below |
| `test_manual_provider_migration.py` | PASS | Same cycle in its own container, part of the batch above |
| Committed `docs/frontend-handoff/openapi.json` vs `app.openapi()` | IDENTICAL | 120 paths, no path or schema differs |

**Migration probe** (`migprobe.py`, own container, revisions by id):

| Step | `ck_payments_manual_never_processing` | `ix_payments_awaiting_manual` | `manual_payment_hold_period` | `payment_provider` enum |
|---|---|---|---|---|
| `upgrade head` → `941b40d285ce` | `CHECK ((provider <> 'manual') OR (status <> 'processing'))` | `btree (initiated_at, id) WHERE provider = 'manual' AND status = 'pending'` | `604800 duration` | `mock,cash,manual` |
| `downgrade 089f97a72014` | gone | gone | gone | `mock,cash,manual` (kept, as the migration documents: PostgreSQL cannot drop an enum value) |
| `upgrade head` again | restored, same definition | restored, same definition | `604800 duration` | `mock,cash,manual` |

## 4. Requirement checklist

Test files: `A` = `tests/integration/payments/test_manual_provider_api.py`, `S` = `tests/integration/payments/test_manual_provider_service.py`, `R` = `tests/concurrency/test_manual_payment_races.py`.

| Requirement | Status | Code | Test |
|---|---|---|---|
| `payment_provider` gains `manual`; CHECK and partial index | DONE | `941b40d285ce…py:40-50`; `payments/infrastructure/models.py:141-175` | `test_order_payment_schema.py` (`manual-payment-processing`, `test_every_lookup_index_exists`); migration test (M01, M02a red). Index predicate: see A-03 |
| Setting `manual_payment_hold_period`: 7 d, 1 h–30 d, internal, seeded | DONE | `settings_registry.py:141-152`; migration `:51-63` | `test_settings_registry.py:355`; `test_settings_seed.py` (M38, M39, M40 red) |
| `ManualPaymentProvider`: no status query, no webhooks, no reference, no redirect | DONE | `providers/manual.py:17-34` | `test_provider_contract.py::test_the_manual_adapter_creates_nothing_and_takes_no_webhooks` (M44 red) |
| `PAYMENT_PROVIDER=manual` boots everywhere; mock still refused in production | DONE | `providers/factory.py:27-30` | `test_provider_factory.py:54` (M37 red) |
| `manual` known by name, configured or not | DONE | `verification.py:64-68` | `S::test_confirm_needs_no_configured_adapter_for_manual`, `::test_the_job_releases_a_manual_order_even_with_no_adapter_configured` (M11 red) |
| Checkout: `pending_payment`, `pending` attempt, no reference or redirect, `next_step: await_admin_contact`, `hold_expires_at` = placed + 7 d | DONE | `checkout.py` (service) `:225-237`; `checkout_schemas.py:135-141, 212-217`; `customer_view.py:26-35` | `A::test_an_stl_checkout_waits_for_the_administrators_call` (M28 red) |
| Q1: STL-only cart on `manual` needs `contact_phone` (422 `CONTACT_PHONE_REQUIRED`, nothing written); other providers refuse one | DONE | `fulfillment.py:40-47`; `checkout.py` (service) `:142` | `A::test_a_manual_stl_checkout_without_a_phone_writes_nothing`; `test_fulfillment_rules.py:81, :92` (M21, M22, M23, M24 red) |
| Q1: offer checkout needs the phone on `manual`, refuses it otherwise | DONE | `offer_checkout.py` (service) `:156-164` | `A::test_an_offer_checkout_needs_the_phone_and_is_paid_by_confirm`, `::test_another_provider_refuses_a_phone_on_an_offer_checkout` (M19, M20 red) |
| Retry onto `manual` without a phone: 422 | DONE | `retry.py:76-78` | `A::test_a_manual_retry_on_an_order_without_a_phone_is_422` (M16 red). Probe P2: retry with a phone from another provider works and alerts |
| Q2: customer `order.awaiting_payment` notice and `order_awaiting_payment` email, never the phone | DONE | `notices.py:54-74`; called from `checkout.py:256-257`, `offer_checkout.py:150-151` | `A` T2 and offer test (`phone_leaks == 0`) (M26a, M26b, M27 red) |
| Q2: one `manual_payment_due` alert per attempt, in Tx1, at checkout, offer checkout and retry | DONE | `api/checkout.py:384-385, 428-436`; `api/offer_checkout.py:204`; `api/payment_retry.py:291`; `payments/public.py` `announce_manual_payment` | `A` T2, offer test, wrong-amount test (retry), `::test_the_alert_commits_with_the_order_even_if_the_second_transaction_fails` (M25a-c red) |
| Confirm: reference optional for `manual` only, blank is none, trimmed, case kept, unique per provider | DONE | `payments/domain/manual.py:32-33`; `infrastructure/manual.py:54, 77-78, 188-195` | `S::test_confirm_without_a_reference_pays_and_moves_the_stl_line`, `::test_a_blank_reference_is_none_and_a_given_one_is_trimmed_case_kept`, `::test_any_other_provider_still_needs_its_reference`; `A::test_a_given_reference_must_be_unique_and_others_still_need_one`; `test_manual_confirm_rules.py:63, :72` (M03, M06, M07, M41 red). Caveat: A-01 |
| Q4: record-capture reference optional for `manual`, stored and unique when given | DONE | `payments/domain/manual.py:66-67`; `infrastructure/manual.py:145-153` | `A::test_a_wrong_amount_is_refused_recorded_as_a_late_capture_and_retried`; `test_manual_confirm_rules.py:110` (M04, M08, M09 red) |
| Two confirms typing one reference: one paid, one 409 (advisory lock) | DONE | `payments.py:86-90`; `manual.py:192` | `R::test_one_reference_typed_on_two_payments_pays_one` (M05 red) |
| Webhook route answers 404 for `manual`, stores nothing | DONE | `api/webhooks.py:108` | `A::test_the_manual_provider_takes_no_webhooks` (M10 red). Probe P4: `webhook_events` count unchanged. Nit A-04 |
| Reconciliation skips `manual` without an alert | DONE | `reconcile.py:121-123` | `S::test_reconciliation_never_asks_or_alerts_about_a_manual_attempt` (M15 red) |
| Hold chosen by the latest attempt's provider; retry bound by it | DONE | `payment_recovery.py:35-47`; `retry.py:66, 97`; `order_history.py:99`; `release.py:147`; `admin_payments.py:472` | `test_payment_recovery_rules.py:197, :204`; `A` wrong-amount and order-detail tests; `S` deadline test (M13, M17, M18, M29, M30, M34, M42 red) |
| Job: not due at +1 h and deadline − 1 s; released exactly at the deadline (`expired`, cancelled, notice, email, audit `manual_hold_expired`, STL freed) | DONE | `release.py:90-91, 147-157, 261-265`; `payments/domain/release.py:125-129` | `S::test_the_job_releases_a_manual_order_exactly_at_its_own_deadline`; `test_release_rules.py:144` (M12, M36, M43 red). Candidates by the shorter hold: M14 red (`test_release_job.py`). Probe P1: a `failed` latest attempt is released too |
| Money after the release: late capture with its refund | DONE | existing `apply_result` | `S::test_a_payment_after_the_release_is_a_late_capture_with_its_refund` |
| Q3: administrator may release a `manual` order at any time, reason mandatory | DONE | `release.py:361-379`; `payment_recovery.py:79-86` | `S::test_the_administrator_may_release_a_manual_order_at_once`; `test_payment_recovery_rules.py:212` (M35 red). Probe P6: the admin payment detail offers `release_order` with `manual_release_available_at` = placement |
| Admin work list `awaiting_confirmation=true`: live `manual` only, oldest first, `hold_expires_at`, no customer contact | DONE | `admin_reads.py:68-80, 119-120`; `admin_payments.py:470-477` | `A::test_the_admin_work_list_holds_only_live_manual_attempts` (asserts the seeded `buyer@example.com` is absent, so not vacuous) (M32, M33, M34 red) |
| Order detail `next_step` only while the attempt is live | DONE | `customer_view.py:30-31`; `order_schemas.py:219-221` | `A::test_the_order_detail_shows_the_next_step_only_while_waiting`; `test_customer_view.py:197, :208` (M31 red) |
| Physical delivery and mixed pickup orders paid by confirm (STL `awaiting_delivery`, physical `pending`) | DONE | existing `apply_result` | `A::test_confirm_without_a_reference_pays_a_mixed_order`, `::test_a_physical_delivery_order_is_paid_with_the_address_phone` |

### "Done when" and FR cases → tests

| Case | Test |
|---|---|
| Done when: cart (STL, physical, mixed) and accepted offer checked out on `manual`, confirm makes it `paid` with STL lines `awaiting_delivery` | `A`: STL (T2 + `S` confirm), mixed pickup, physical delivery, offer tests |
| Done when: an unpaid manual order is released at its deadline | `S::test_the_job_releases_a_manual_order_exactly_at_its_own_deadline` |
| Done when: SRS sections updated, ADR-049 Accepted | Verified by grep: BR-039, BR-052, BR-054, §7.3 steps 9-10, §7.4 table, §9.1-9.3, §15.4, §20.8, §23, §30.4; ADR-049 Status Accepted; `settings-registry.md` (seventeen), `notification-contract.md` |
| FR-06 neg: STL-only or offer checkout on `manual` without a phone → 422; another provider refuses one | `A` T2b and both offer tests |
| FR-06 neg: retry onto `manual` without a phone → 422 | `A::test_a_manual_retry_on_an_order_without_a_phone_is_422` |
| FR-07 neg: a reference already on another payment is refused, also for two racing confirms | `A::test_a_given_reference_must_be_unique…`, `R::test_one_reference_typed_on_two_payments_pays_one` |
| FR-07 neg: `manual` takes no webhooks and is never reconciled | `A::test_the_manual_provider_takes_no_webhooks`, `S::test_reconciliation_never_asks…` |
| FR-07 neg: unauthorised users cannot confirm | Existing admin-boundary matrix (unchanged route) |
| FR-07 failure: a `manual` order is released at the hold's end; money after it is a late capture | `S` deadline and late-capture tests |
| Concurrency C1: confirm vs the job's release, both orders | `R::test_a_confirm_and_the_release_at_the_deadline_never_both_win[release|confirm]` |
| Concurrency RF6: admin release vs confirm, both orders | `R::test_an_admin_release_and_a_confirm_never_both_win[release|confirm]` |
| Concurrency C3: one payment confirmed twice | `R::test_one_payment_confirmed_twice_is_paid_once` (one `payment.verified` audit row) |

## 5. Definition of Done

| Checkbox | Met? | Evidence |
|---|---|---|
| Migration reviewed, reversible, one head | Met | Probe above; one head `941b40d285ce`; the enum value is kept on downgrade, documented in the migration |
| Rules in the owning context; other contexts via ports | Met | Payments reaches Ordering only through `app.ordering.public` (`read_holds`, `Holds`, `MANUAL_PROVIDER`, `Order`); Ordering's API calls `app.payments.public.announce_manual_payment`. `test_deep_architecture.py` passes in the unit run |
| Auth, verified email, ownership 404, admin boundary, CSRF, rate limits | Met | No new route. The new query parameter sits on the existing admin GET; confirm and record-capture keep CSRF and their rate limits. Retry and order detail keep the owner's 404 |
| Money in cents; UTC; server computes status | Met | Confirm still refuses a differing amount or currency before any lock; holds are `timedelta` on `timestamptz`; order status through `apply_result` and `release_unpaid_order` |
| Audit, notification, outbox in the same transaction | Met | Customer notice and email in the order's transaction; admin alert as Tx1's last write (`A::test_the_alert_commits_with_the_order_even_if_the_second_transaction_fails`); the release audit row and notice in Tx B |
| Background jobs registered, idempotent, tested | Met | No new job; `release_stale_checkouts` and `reconcile_payments` extended, re-check under locks, tested (`S`, C1) |
| Unit + PG integration + API error/IDOR + a concurrency test per race | Met | C1-C3 and RF6 race tests, all with `meet_or_fail` |
| Each "Done when" covered; ruff, mypy, pytest green in CI | Met | §3, §4 |
| Docs and OpenAPI updated; Status Done | Met | `openapi.json` identical to `app.openapi()`; plan Status Done; README and CLAUDE.md list VS-050 as done; nit A-02 |
| Glossary naming | Met | `Payment`, `Order`, `provider_payment_id`, `contact_phone_snapshot`; the glossary gained a Manual Payment Provider entry |

Test strength: no `caplog` assertions; every race uses `tests/concurrency/barrier.py::meet_or_fail` and staggers the second racer after the first order lock; no timing claims. The deadline test checks both sides of the boundary (deadline − 1 s, deadline).

**Mutation results.** Scratch copy of `origin/main`, `PYTHONPATH` pointed at its `src` (verified), `.env.example` values in the process environment as CI does. Target set: `tests/unit/payments`, `tests/unit/ordering`, the registry unit test, the provider contract, the order/payment schema test, `A`, `S`, `R`, the migration test, and the existing `test_release_job`, `test_reconcile_job`, `test_manual_recovery`, `test_admin_payment_reads`, `test_webhook_api`, `test_settings_seed`. **Baseline: 1372 passed.** Each mutation ran alone with `-x`, its likely killer first, then the whole target set; the file was restored after each one.

| Mutation (scratch copy only) | Result: first failing test |
|---|---|
| M01 drop `ck_payments_manual_never_processing` (migration) | RED: `test_the_database_refuses_the_row[manual-payment-processing]` |
| M02a drop `ix_payments_awaiting_manual` (migration) | RED: `test_every_lookup_index_exists` |
| M02b make that index non-partial | RED, **incidentally**: `test_reconcile_job.py::test_the_selection_uses_ix_payments_unsettled` (the planner picks the wider index). See A-03 |
| M03 confirm: any provider may omit the reference | RED: `test_only_manual_may_omit_the_reference[False]` |
| M04 record-capture: same | RED: `test_record_capture_refusals_in_order` |
| M05 drop the `(provider, reference)` advisory lock | RED: `R::test_one_reference_typed_on_two_payments_pays_one` |
| M06 drop the other-owner reference check | RED: `S::test_a_blank_reference_is_none_and_a_given_one_is_trimmed_case_kept` |
| M07 drop the own-reference mismatch check | RED: `test_manual_recovery.py::test_a_reference_that_differs_or_belongs_to_another_payment_is_refused` (VS-024's test) |
| M08 record-capture stores no `manual` reference | RED: `A::test_a_wrong_amount_is_refused_recorded_as_a_late_capture_and_retried` |
| M09 record-capture skips the uniqueness check | RED: same test |
| M10 webhook route accepts `manual` | RED: `A::test_the_manual_provider_takes_no_webhooks` |
| M11 `capability()` no longer knows `manual` by name | RED: `S::test_the_job_releases_a_manual_order_even_with_no_adapter_configured` |
| M12 job never answers `expired` for `manual` | RED: same test |
| M13 `Holds.for_provider` always the online hold | RED: `test_the_hold_is_chosen_by_the_attempt_provider[manual-hold0]` |
| M14 candidates selected with the manual hold | RED: `test_release_job.py::test_an_explicit_answer_releases_the_order[failed-1930]` |
| M15 reconciliation no longer skips `manual` | RED: `S::test_reconciliation_never_asks_or_alerts_about_a_manual_attempt` |
| M16 retry onto `manual` without a phone allowed | RED: `A::test_a_manual_retry_on_an_order_without_a_phone_is_422` |
| M17 retry bound by the online hold | RED: `A::test_a_wrong_amount_is_refused_recorded_as_a_late_capture_and_retried` |
| M18 retry `hold_expires_at` from the online hold | RED: same test |
| M19 offer on `manual` without a phone allowed | RED: `A::test_an_offer_checkout_needs_the_phone_and_is_paid_by_confirm` |
| M20 offer on another provider accepts a phone | RED: `A::test_another_provider_refuses_a_phone_on_an_offer_checkout` |
| M21 STL-only `manual` without a phone allowed | RED: `test_a_manual_stl_only_order_takes_the_phone_to_call_and_needs_it` |
| M22 STL-only non-manual accepts a phone | RED: same test |
| M23 checkout never asks for the phone to call | RED: `A::test_an_stl_checkout_waits_for_the_administrators_call` |
| M24 `chooses_manual` false for a manual-only configuration | RED: `test_chooses_manual[None-configured1-True]` |
| M25a/b/c no admin alert at cart checkout / offer checkout / retry | RED: `A` T2 / offer test / wrong-amount test |
| M26a/b no customer notice at cart / offer checkout | RED: `A` T2 / offer test |
| M27 the customer notice carries the phone | RED: `A` T2 (`phone_leaks`) |
| M28/M29 checkout / offer `hold_expires_at` from the online hold | RED: `A` T2 / offer test |
| M30 order detail hold from the online hold | RED: `A::test_the_order_detail_shows_the_next_step_only_while_waiting` |
| M31 `next_step` shown for an attempt that is over | RED: `test_an_attempt_that_is_over_has_no_next_step[manual-paid]` |
| M32 `awaiting_confirmation` filter ignored | RED: `A::test_the_admin_work_list_holds_only_live_manual_attempts` |
| M33 `needs_manual_confirmation` false for a pending `manual` attempt | RED: same test |
| M34 work-list `hold_expires_at` from the online hold | RED: same test |
| M35 admin release of `manual` waits for the grace | RED: `S::test_the_administrator_may_release_a_manual_order_at_once` |
| M36 job audit reason not `manual_hold_expired` | RED: `S::test_the_job_releases_a_manual_order_exactly_at_its_own_deadline` |
| M37 factory without the `manual` adapter | RED: `test_manual_boots_in_every_environment[production]` |
| M38 registry default 1 day instead of 7 | RED: `test_the_manual_hold_is_seven_days_editable_from_one_hour_to_thirty_days` |
| M39 registry minimum 1 minute | RED: same test |
| M40 migration seeds 1 day | RED: `test_settings_seed.py::test_the_seeded_values_are_the_registry_defaults` |
| M41 confirm reference not trimmed | RED: `S::test_a_blank_reference_is_none_and_a_given_one_is_trimmed_case_kept` |
| M42 job's per-order hold is the online hold | RED: `S::test_the_job_releases_a_manual_order_exactly_at_its_own_deadline` |
| M43 T2 treats `manual` as no-status-query | RED: `test_release_rules.py::test_a_manual_attempt_is_answered_by_the_platform_and_released` |
| M44 manual adapter claims a status query | RED: `test_the_manual_adapter_creates_nothing_and_takes_no_webhooks` |

48 of 48 killed. A first M38 run targeted the first `default=604_800` in the registry (`offer_rejection_cooldown`) by mistake; it was re-run against `manual_payment_hold_period` (above). The plan's equivalent mutant (skipping `set_provider_reference` for `None`) was not re-run.

**Probes** (scratch-only test file, 6 passed): P1 the job releases a `manual` order whose latest attempt is `failed`; P2 retry from another provider onto `manual` with a phone → 201 and one alert; P3 one customer holds four unpaid `manual` orders (Q-1); P4 a webhook to `manual` stores no `webhook_events` row; P5 a `noop` confirm writes a reference (A-01); P6 the admin payment detail offers `release_order` two hours into the hold.

## 6. Findings

| ID | Sev | Location | What is wrong | Why it matters | Suggested fix (not applied) | Scope | Status |
|---|---|---|---|---|---|---|---|
| A-01 | Minor | `payments/infrastructure/manual.py:77-86`; `payments/application/services/apply.py:53-54` | A confirm of a `manual` attempt that is already `paid` with no reference, sent with a reference, returns 200 `noop` but stores that reference as the paid attempt's `provider_payment_id`. **Probe P5:** confirm without a reference → `apply_paid`; confirm again with `second-251a93` → 200 `{"outcome": "noop"}`, and the row now has `provider_payment_id = 'second-251a93'`. The same holds for an attempt already late-captured | ADR-049 calls a confirm of a paid attempt a `noop`, and the duplicate-transfer case is meant to be settled outside the system. Instead, the paid attempt's recorded reference names the second (duplicate) transfer, not the one that paid it, and that reference is now taken, so it cannot be recorded anywhere else | Pass the reference to `apply_provider_result` only when the attempt is still live or not yet late-captured (re-read under the payment lock), or refuse a reference on an attempt that has already reached paid or is late-captured (409 `INVALID_STATE_TRANSITION`). Add an API test | VS-050 | **Fixed** (branch `fix/vs050-audit-findings`): `second_transfer` (`payments/domain/manual.py`) under the payment lock; 409 `PAYMENT_ALREADY_PAID_OTHER_REFERENCE`. Tests: `test_an_attempt_holding_money_keeps_its_reference` (unit), `A::test_a_paid_attempt_keeps_its_reference_and_flags_a_second_transfer[None\|OMT-first]`, `S::test_a_late_captured_attempt_keeps_its_reference`. Review fix: a reference another payment has stays 409 `PAYMENT_REFERENCE_MISMATCH` (`A::test_another_payments_reference_on_a_paid_attempt_is_a_mismatch_not_a_transfer`) |
| A-02 | Nit | `payments/infrastructure/admin_reads.py:28` | The comment cites "ADR-049 d8" for the work list; d8 is the phone to call, d11 is the work list (`models.py:170` cites d11 correctly) | Misleading cross-reference | Change to d11 | VS-050 | **Fixed**: the comment cites d11 |
| A-03 | Nit | `test_order_payment_schema.py:806-819`; `test_manual_provider_migration.py` | Nothing pins the partial predicate of `ix_payments_awaiting_manual`: both tests only count the index. M02b (non-partial) was caught only by an unrelated plan test for `ix_payments_unsettled` | The work list's index could silently lose its predicate if that other plan test changes | Assert `indexdef` contains `WHERE ((provider = 'manual'…) AND (status = 'pending'…))`, as `test_the_stl_delivery_queue_index_is_partial_on_created_at_and_id` does | VS-050 (tests) | **Fixed**: `test_the_manual_work_list_index_is_partial_on_initiated_at_and_id` |
| A-04 | Nit | `A::test_the_manual_provider_takes_no_webhooks` | Plan T9 says "404, nothing stored"; the test asserts only the 404. Probe P4 shows nothing is stored today | Low risk: the 404 is the route's first check | Count `webhook_events` before and after | VS-050 (tests) | **Fixed**: the test counts `webhook_events` before and after |

Also checked, no issue found:
- `chooses_manual` and `choose_provider` agree: both compare exactly, so no spelling of a provider name can skip the phone check.
- A delivery order's phone comes from the address, so a retry onto `manual` of a delivery order has a phone.
- The admin alert payload carries the order number and provider only.
- The work-list response carries no customer email.
- The release audit reason distinguishes `manual_hold_expired`.
- Admin release of a `manual` order is offered from placement.
- The committed OpenAPI is current.

## 7. Open questions

- **Q-1 (resolved, owner 2026-11-02: cap added).** Setting `manual_max_open_orders` (default 3, 1-10), checked at cart and offer checkout under a per-customer advisory lock, `422 MANUAL_ORDER_LIMIT_REACHED`; ADR-049 d14, migration `95ffee5fde3b`; race test `tests/concurrency/test_manual_order_cap_races.py`. Original question: **no cap on open unpaid `manual` orders per customer.** Probe P3: one verified customer placed four `manual` orders in a row: all 201, four `pending_payment` orders and four `manual_payment_due` alerts. The only limit is checkout's 30 per hour per user (`payments/domain/limits.py:36`). With a 7-day hold, one account can hold up to about 5,000 unpaid orders, each alerting every administrator (by email once VS-021 is built), and each holding its STL ownership index. Cash has `cash_max_open_orders`; the SRS sets nothing for `manual`. Does the owner want a per-customer cap on open `manual` orders, or is the rate limit enough for V1?
- **Q-2 (resolved, owner 2026-11-02: accepted; the frontend shows "to cancel an unpaid order, contact us" with the WhatsApp link, `BACKEND-RESPONSE.md` C6).** Original question: **the customer cannot cancel their own unpaid `manual` order** for up to 7 days. Self-cancel covers `in_progress` and `partially_refunded` only. That blocks their account deletion and the same STL's re-checkout until the administrator releases the order. ADR-049 records this as a consequence; confirm it is acceptable for the customer-facing flow (the frontend should say "contact us to cancel").

## 8. How the commands were run

- Local commands used the repo's `.venv`. The checkout's `.env` was neither read nor copied (the hooks block it). The integration suites set their own environment and testcontainers. For the scratch copy, the driver loaded `.env.example`'s values into the process environment, as CI does with `cp .env.example .env`.
- Integration batch: `test_manual_provider_api`, `test_manual_provider_service`, `test_manual_provider_migration`, `test_order_payment_schema`, `test_settings_seed`, `test_reconcile_job`, `test_manual_recovery`, `test_mock_provider`, `test_release_money_risk`, `test_provider_contract`, `test_order_history_api`, `test_cash_order_exclusions`. Concurrency batch run separately. The full suite was not run locally (machine memory); CI results are quoted with run ids.
- The first mutation run was stopped by Claude Code for low system memory after 29 of 48 mutations. The interrupted mutation's file was restored from a pristine archive and checked with `diff -rq`. The remaining 19 were then run with the user's approval. The scratch copy and the repo were verified clean afterwards.
- Scratch artefacts (outside the repo): `mutate.py` (driver), `mutations.jsonl` (one record per mutation), `migprobe.py`, `mut/tests/integration/payments/test_zz_audit_probes.py`.
