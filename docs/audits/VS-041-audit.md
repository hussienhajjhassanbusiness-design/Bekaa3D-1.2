# VS-041 audit: the money path (cart, checkout and verification, payment recovery, offer checkout)

Independent, read-only audit of VS-022, VS-023, VS-024 and VS-041 together. Auditor dates: 2026-10-21 to 2026-10-22. Tree audited: `main` @ `93268a0` (clean). No source, test, migration or status file was changed, and nothing was committed. Mutations and probes ran only on a `git archive 93268a0` copy in the session scratchpad.

## 1. Verdict

**Yes, with minor gaps.** The money path is well defended. Every suite it owns passes on real PostgreSQL: 1,075 tests across ordering, payments, negotiation, the races, smoke, e2e, security and migrations. CI is green on the audited commit (4,691 passed). The four migrations go down and come back cleanly. Of 62 mutations aimed at the guards that matter (locks, indexes, CHECKs, amount and currency checks, ownership filters, kill switches, idempotency, error translations, audit writes, rate limits and the ADR-024 lock order), 53 are killed. Of the 9 survivors, 3 are equivalent or unreachable (R2, O1, O12) and 6 are real test gaps (K6, P6, J1, J2, K9, O13). Every race test synchronises through `meet_or_fail`.

What survives is narrow:
- The refusal of a **zero-total checkout** has no test. Removing it lets a $0 STL order and a $0 payment attempt through, and products may be priced at 0 (A-01).
- The FR-07 rule that a webhook event whose provider differs from its payment's provider is "stored and ignored" has no test, although the VS-023 plan lists one (A-02).
- The daily `purge_expired_idempotency_records` job has no test at all. Unregistering it, or breaking its batch loop, goes unnoticed (A-03).
- The 30-per-hour limit shared by cart checkout and offer checkout is never exercised. Removing it from either route goes unnoticed (A-04).

Close A-01 before VS-028 adds cash and physical checkout around the same `place_order`.

## 2. Repo state (Phase 1)

| Item | Finding |
|---|---|
| Branch / commit | `main` @ `93268a04fcdfc1d26e641862cdff6fca78387688` ("ADR-035: PR #25 questions decided as built", #28) |
| Uncommitted/untracked | None at the start. Afterwards the only untracked file is this report |
| Slices on `main`? | Yes. VS-022: `dd76d2c` to `2731e6d`. VS-023: `5f6fd49` to `f44a8aa`. VS-024: `2c11cab` to `ca97518`, merged in `056a0fd` (#24). VS-041: `7003f8c` (#26), which also wired `can_retry_payment` and `hold_expires_at` into `OrderDetail`. `bf0abd1` (#25) touched offer acceptance |
| Money-path migrations | `bde6135b2538` (carts), `03a4730dd046` (orders, payments, webhooks, idempotency), `00ce1ce252a6` (captured amount), `d5507ee63176` (`uq_order_items_offer_once`) |
| Later work on `origin/main` | `ab3ee0c` (#27, VS-028 PR A schema) landed during the audit. It is **not** audited here |

## 3. Command results (Phase 2)

| Command | Result | Notes |
|---|---|---|
| `ruff check .` | PASS | "All checks passed!" |
| `ruff format --check .` | PASS | 765 files already formatted |
| `mypy src tests` (strict) | PASS | 658 source files, no issues |
| `pytest tests/unit` | PASS | 1585 passed, 58 s (includes `test_deep_architecture.py`) |
| `pytest tests/integration/ordering` | PASS | 291 passed, 0 skipped, 3 min 25 s |
| `pytest tests/integration/payments` | PASS | 200 passed, 2 min 25 s |
| `pytest tests/integration/negotiation` | PASS | 270 passed, 2 min 24 s |
| Concurrency: `test_cart_races`, `test_checkout_races`, `test_offer_checkout_races`, `test_offer_races`, `test_offer_action_races`, `test_payment_alert_races`, `test_payment_races`, `test_payment_recovery_races`, `test_payment_recovery_more_races`, `test_payment_retry_races` | PASS | 242 passed, 3 min 04 s |
| Smoke VS-022/023/024/041, `tests/e2e`, `tests/security/test_payment_*`, `tests/contract/payments`, `test_deep_db_constraints_and_migrations`, `test_migration_reversibility`, `test_model_migration_parity`, `test_migrations` | PASS | 72 passed, 1 min 16 s |
| **GitHub Actions, full suite on `93268a0`** (run 39503985134) | PASS | **4691 passed, 1 skipped, 8 deselected (`timing`)**, 30 min 08 s. CI's result, not a local run |
| `alembic heads` | PASS | Exactly one head: `d5507ee63176` |
| upgrade → downgrade → upgrade, per migration, on a throwaway `postgres:16` container | PASS | See below |

The first local attempt failed with 291 setup errors because Docker Desktop had stopped (`DockerException: Error while fetching server API version`). I restarted Docker and re-ran everything; only the second run is reported. No local suite had a skip, xfail or error.

**Migration cycle.** I probed 18 objects (8 tables, 4 partial unique indexes and 6 named constraints) at head, after `downgrade` to each money migration's parent, and after `upgrade head` again:

| Downgrade to | Objects gone | Back after upgrade |
|---|---|---|
| `8d2f6a1c3e57` (below `d5507ee63176`) | `uq_order_items_offer_once` | all 18 |
| `03a4730dd046` (below `00ce1ce252a6`) | `ck_payments_captured_shape`, `ck_payments_captured_when`, and the offer-once index above it | all 18 |
| `26d5d039d72c` (below `03a4730dd046`) | 14: the six order/payment tables, `uq_order_items_stl_ownership`, `uq_payments_one_live`, `uq_payments_one_cash`, `ck_payments_paid_verified`, `uq_webhook_events_provider_event`, … | all 18 |
| `75ad58ebd9e5` (below `bde6135b2538`) | all 18, including `uq_products_id_type` and `ck_cart_items_stl_quantity_one` | all 18 |

### Mutation results (Phase 4)

Each mutation is one exact string replacement on the scratch copy (asserted to match once), run against its area's target tests with `-x`, then reverted. Baseline over the union of the target sets: **1388 passed**, 15 min 35 s. The survivors K6, P6, R2 and O1 were re-run against the full money-path union plus `tests/integration/negotiation` (1626 tests). O11 was re-run with the VS-040 offer-action tests. J1 and J2 ran against `tests/unit` and the idempotency-store tests. The full-union re-run of K9 and O13 was stopped by the host (see §8); their result stands on the checkout and offer targets plus the grep in A-04.

Target sets: **cart** (`tests/unit/ordering`, `test_cart_api`, `test_cart_schema`, `test_cart_races`, VS-022 smoke); **checkout** (unit ordering and payments, `test_checkout_api`, `test_checkout_crash_window`, `test_stl_ownership_api`, `test_order_payment_schema`, `test_checkout_no_open_transaction`, `test_checkout_races`, VS-023 e2e and smoke, `test_payment_security`); **pay** (unit payments, `tests/integration/payments`, the four payment race files, `tests/e2e`, both payment security files); **retry** (unit ordering, the retry, hold-deadline, route lock-order, release-unpaid-order and lock-order integration files, `test_payment_retry_races`, VS-024 e2e and smoke, recovery security); **offer** (unit negotiation and ordering, the offer-checkout API/schema files, offer e2e, expiry and settlement files, `test_offer_checkout_races`, VS-041 smoke).

| # | Mutation | Result (first failing test) |
|---|---|---|
| C1 | drop `FOR UPDATE` on the cart lock (`carts.py:69`) | RED `test_n_concurrent_first_adds_of_one_product_merge_into_one_line` |
| C2 | drop `ck_cart_items_stl_quantity_one` from the migration | RED `test_cart_schema.py::test_the_database_refuses_invalid_lines[stl-…-2-…]` |
| C3 | cart: skip the owned-STL refusal | RED `test_adding_an_owned_stl_is_409_product_already_owned` |
| C4 | 50-line limit `>=` → `>` | RED `test_the_fiftieth_line_is_allowed_and_the_fifty_first_is_not` |
| C5 | merge cap `merged > cap` → `> cap + 1` | RED `test_a_first_physical_add_is_bounded_by_the_cap` |
| C6 | checkout over-cap `>` → `> cap + 1` | RED `test_every_unbuyable_line_is_named` |
| K1 | checkout ignores `accepting_orders` | RED `test_the_kill_switch_is_503_but_still_replays_an_earlier_success` |
| K2 | skip the price-change check | RED `test_a_changed_price_is_refused_with_the_new_price_and_nothing_is_charged` |
| K3 | skip dropping STLs owned since they were added | RED `test_an_stl_bought_since_it_was_added_is_dropped_and_named` |
| K4 | skip the STL final-sale consent | RED `test_a_refused_request_is_422_and_leaves_the_cart[consent]` |
| K5 | ownership-index violation no longer translated (→ 500) | RED `test_an_stl_held_by_the_customers_own_unpaid_order_is_409_not_500` |
| **K6** | **drop the zero-total refusal (`checkout.py:98-99`)** | **GREEN (survives; K6x on the full union: 1626 passed)** → A-01 |
| K7 | price lines from the cart snapshot, not the live price | RED `test_lines_are_priced_live_never_from_the_snapshot` |
| K8 | idempotency: a different body is not a conflict | RED `test_the_same_key_with_a_different_body_conflicts` |
| P1 | `decide`: captured amount not compared with the order total | RED `test_a_mismatched_capture_is_never_applied[stale-attempt]` |
| P2 | `decide`: pay a cancelled order | RED `test_a_late_capture_stores_the_answer_then_calls_the_sink[cancelled-order]` |
| P3 | `decide`: drop the USD check | RED `…_calls_the_sink[currency]` |
| P4 | `decide`: a repeat late capture is recorded again | RED `test_the_decision_uses_the_locked_rows_not_the_pre_read[late-already]` |
| P5 | `apply_result` locks the payment before the order (ADR-024) | RED `test_paid_writes_the_answers_amount_after_the_three_locks` |
| **P6** | **webhook: drop the `provider_mismatch` check (`webhooks.py:35-36`)** | **GREEN (survives; P6x on the full union: 1626 passed)** → A-02 |
| P7 | webhook: drop the `reference_mismatch` check | RED `test_an_event_whose_reference_contradicts_the_payment_is_ignored` |
| P8 | route any provider path to the mock adapter | RED `test_an_unconfigured_provider_is_404_and_touches_nothing[cash]` |
| P9 | `mark_failed` no longer restricted to `pending` | RED `test_mark_failed_never_undoes_a_paid_attempt` |
| P10 | webhook insert loses `ON CONFLICT DO NOTHING` | RED `test_receipt_and_tx_a_lock_nothing_and_the_event_is_processed_last` |
| P11 | manual confirm: amount no longer compared | RED `test_a_differing_amount_or_currency_is_refused[…-999-USD]` |
| P12 | manual confirm: a reference owned by another payment accepted | RED `test_a_reference_that_differs_or_belongs_to_another_payment_is_refused` |
| P13 | manual confirm allowed on a status-query provider | RED `test_a_status_capable_provider_is_reconciled_instead` |
| P14 | skip the `payment.manual_confirmation` audit write | RED `test_a_manual_confirm_pays_and_audits_the_typed_amount_and_reason` |
| P15 | drop `FOR UPDATE` on `orders` (`lock_order`) | RED `test_a_manual_release_locks_orders_lines_then_payments` |
| P16 | payment no longer settles offers | RED `test_negotiate_accept_pay_and_close_the_offer_as_paid` |
| R1 | release: drop the `events > 0` re-check under the locks | RED `test_an_event_that_arrives_during_the_question_stops_the_release` |
| R2 | release: drop the `latest.id != asked.id` re-check | GREEN (R2x on the full union: 1626 passed). **Equivalent**: a newer attempt always moves `hold_deadline` past `now`, and the post-apply "every attempt failed or expired" check also refuses |
| R3 | `pending` treated as an explicit release answer | RED `test_only_failed_and_expired_ever_release` |
| R4 | unprocessed events ignored before asking | RED `test_only_failed_and_expired_ever_release` |
| R5 | job ignores the per-order hold deadline | RED `test_an_order_behind_120_skipped_orders_is_released_in_the_same_run` |
| R6 | release despite a non-dead attempt after apply | RED `test_an_older_live_attempt_blocks_the_release` |
| R7 | manual release ignores the grace period | RED `test_the_detail_shows_order_events_history_and_actions_without_secrets` |
| R8 | manual release ignores unreviewed events | RED `test_unprocessed_events_need_events_reviewed` |
| R9 | skip the manual release's `payment.expired` audit | RED `test_a_release_after_the_grace_cancels_with_the_admin_on_every_row` |
| R10 | `release_unpaid_order` accepts a paid order | RED `test_only_an_unpaid_uncancelled_online_order_is_released[paid]` |
| T1 | retry allowed on a cancelled order | RED `test_can_retry_payment_is_false_for_paid_cash_and_cancelled_orders` |
| T2 | retry hold `>=` → `>` | RED `test_can_retry_payment_is_false_once_the_hold_ends` |
| T3 | retry loses the ownership filter (IDOR) | RED `test_another_users_order_and_an_unknown_one_get_the_same_404` |
| T4 | retry loses `FOR UPDATE` on the caller's order | RED `test_retry_locks_its_claim_then_the_callers_order_and_nothing_else` |
| T5 | retry skips the offer-window check | RED `test_retry_of_an_offer_order_after_the_window_is_refused[deadline]` |
| T6 | one-live index violation not translated | RED `test_the_one_live_index_race_is_a_clean_409_and_leaves_no_claim` |
| O1 | offer re-lock kept, `!= offer` comparison dropped | GREEN (O1x on the full union: 1626 passed). **Equivalent**: the re-lock still re-checks status and window, and the compared fields are immutable once accepted (BR-085) |
| O2 | offer re-lock dropped entirely | RED `test_the_window_closing_while_offer_checkout_places_its_order[job]` |
| O3 | `uq_order_items_offer_once` not created | RED `test_a_second_line_for_one_offer_is_refused[refunded]` |
| O4 | offer checkout ignores `accepting_orders` | RED `test_a_paused_shop_is_503_and_writes_nothing` |
| O5 | offer checkout skips the live-attempt refusal | RED `test_a_second_checkout_while_a_payment_is_live_is_409_payment_already_active` |
| O6 | settlement never auto-closes | RED `test_settle_auto_closes_a_live_offer_bought_another_way[accepted]` |
| O7 | settlement skips the (customer, product) advisory lock | RED `test_settle_pays_the_offer_bought_through` |
| O8 | offer line priced at the list price | RED `test_checkout_charges_the_agreed_price_whatever_the_list_price[500]` |
| O9 | offer window `>=` → `>` | RED `test_checkout_expiry_closes_once_and_tells_the_customer_in_app` |
| O10 | the paid offer is auto-closed instead of `paid` | RED `test_settle_pays_the_offer_bought_through` |
| O11 | `SqlOfferStore.lock` ignores `user_id` | GREEN on the offer and retry targets; **RED** with the VS-040 action tests (O11b): `test_another_customers_offer_is_404[counter]`. Offer checkout also reads through `get(user_id=…)` before it locks |
| O12 | offer-once violation not translated | GREEN. **Unreachable today**: see "Also checked" in §6 |
| J1 | idempotency purge job never stops on a short batch | **GREEN (survives)**: 1596 passed (`tests/unit`, `test_idempotency_store.py`, VS-023 smoke) → A-03 |
| J2 | idempotency purge job unregistered | **GREEN (survives)**: 1596 passed → A-03 |
| **K9** | **cart checkout loses `Depends(checkout_rate_limit)` (`api/checkout.py:256`)** | **GREEN (survives)**: 880 passed on the checkout and offer targets; the full-union re-run was stopped (low memory; see §8) → A-04 |
| **O13** | **offer checkout loses `Depends(checkout_rate_limit)` (`api/offer_checkout.py:134`)** | **GREEN (survives)**: 880 passed; full-union re-run stopped as for K9 → A-04 |

## 4. Requirement checklist (Phase 3)

Sources: the four slice sections of `vertical-slice-plan.md`; FR-05, FR-06, FR-07 and FR-13 (`functional-requirements.md:231-424, 672-728`); BR-058, BR-060, BR-085 to BR-088, BR-148; INV-02, INV-05, INV-08, INV-09, INV-18, INV-21, INV-22; ADR-024, ADR-029, ADR-032, ADR-036, ADR-037; `api-endpoints.md:369, 409, 439, 594-597, 695`.

### VS-022 cart

| Requirement | Status | Code | Test (and mutation) |
|---|---|---|---|
| One cart per user; unique `(cart_id, product_id)`; STL quantity 1 by CHECK on a type snapshot proved by a composite FK | DONE | `bde6135b2538:41-71` | `test_cart_schema.py::test_the_database_refuses_invalid_lines` (C2 red) |
| Adds upsert and merge under the cart lock, then re-check the cap | DONE | `carts.py:60-73`; `cart.py:38-78`; `cart_rules.py:49` | `test_n_concurrent_increments_stop_exactly_at_the_cap`, `test_two_concurrent_adds_of_one_product_stay_within_the_cap` (C1, C5 red) |
| Refused: WhatsApp-only, hidden, deleted, unavailable | DONE | `cart_rules.py:30-32` (Catalog's `purchase_refusal`) | `test_unbuyable_products_are_refused_with_their_reason`, `test_unknown_deleted_hidden_and_category_off_products_answer_identically` |
| Owned STL refused 409 `PRODUCT_ALREADY_OWNED` (VS-023 addition) | DONE | `cart.py:53-59` | `test_adding_an_owned_stl_is_409_product_already_owned` (C3 red) |
| `CartRead`: snapshot price, current price, `price_changed`, `over_cap`, `purchasable` | DONE | `cart_rules.py:93-114` | `test_a_price_change_is_flagged_and_clears_when_restored`, `test_a_lowered_cap_flags_over_cap_and_allows_only_going_down` |
| Unverified user reads but cannot write; CSRF; per-user limit | DONE | `cart.py` routes | `test_an_unverified_user_reads_an_empty_cart_and_cannot_write`, `test_a_write_without_the_csrf_header_is_refused`, `test_the_rate_limit_is_per_user_and_reads_are_never_limited` |
| **Done when**: no duplicate lines, STL ≤ 1, quantity ≤ cap | DONE | as above | the cart race file (9 tests, `meet_or_fail`) |
| FR-05 failure: a failed update leaves the cart unchanged | DONE | single statements under the lock | `test_a_physical_add_over_the_cap_changes_nothing` |

### VS-023 checkout and verification

| Requirement | Status | Code | Test (and mutation) |
|---|---|---|---|
| Idempotency: one checkout per key; same key and body replays; different body 409 | DONE | `idempotency.py:30-72`; `checkout.py` route | `test_the_same_key_and_body_replays_the_stored_201`, `test_the_same_key_with_a_different_body_conflicts`, `test_race_2_…`, `test_race_3_…` (K8 red) |
| Kill switch 503 `ORDERS_PAUSED`; never blocks an in-flight payment | DONE | `checkout.py:74-75` | `test_the_kill_switch_is_503_but_still_replays_an_earlier_success`, `test_the_kill_switch_does_not_block_an_in_flight_payment` (K1 red) |
| Lock the cart and revalidate every line; name every refusal; never drop silently | DONE | `checkout.py:79-83`; `checkout_rules.py:61-80` | `test_lines_that_cannot_be_bought_are_422_naming_every_line`, `test_over_cap_lines_alone_are_422_quantity_exceeds_limit` (C6 red) |
| Price-change check (409 `CART_PRICE_CHANGED` unless accepted) | DONE | `checkout.py:92-93` | `test_a_changed_price_is_refused_with_the_new_price_and_nothing_is_charged` (K2 red) |
| Totals recomputed from the live price; client amounts ignored (INV-02) | DONE | `checkout_rules.py:128-153` | `test_lines_are_priced_live_never_from_the_snapshot`, `test_checkout_places_a_pending_order_at_the_live_price` (K7 red) |
| STL bought since added is dropped and named (SRS §7.3 step 5) | DONE | `checkout.py:86-91` | `test_an_stl_bought_since_it_was_added_is_dropped_and_named`, `test_every_line_owned_is_409_cart_empty_naming_them` (K3 red) |
| Ownership-index violation → 409, not 500 | DONE | `orders.py:99-127` | `test_an_stl_held_by_the_customers_own_unpaid_order_is_409_not_500`, `test_race_4_the_ownership_index_lets_one_live_line_win` (K5 red) |
| BR-060 digital final-sale consent recorded | DONE | `checkout.py:95`; `digital_terms_*` on the insert | `test_a_refused_request_is_422_and_leaves_the_cart[consent]` (K4 red) |
| Zero total refused (`zero_total`, `checkout.md:44`, plan Q8) | **PARTIAL** | `checkout.py:98-99` | **None** (K6 survives): A-01 |
| Physical lines 422 `INVALID_FULFILLMENT` until VS-028 | DONE | `checkout_rules.py:83-88` | `test_a_physical_line_is_422_invalid_fulfillment` |
| Provider called after commit; no transaction open; 502 replayed | DONE | `api/checkout.py:260-334` | `test_checkout_no_open_transaction.py`, `test_a_provider_failure_is_502_keeps_the_order_and_replays`, `test_checkout_crash_window.py` |
| DB: one live payment; unique `(provider, event_id)`; cash CHECKs (INV-21, INV-22); `paid` needs `verified_at` | DONE | `03a4730dd046:204-376` | `test_order_payment_schema.py::test_the_database_refuses_the_row` (parametrised over the constraints) |
| STL ownership partial unique index (INV-18) | DONE | `03a4730dd046:259-268` | `test_race_4_…`, `test_offer_checkout_racing_cart_checkout_yields_one_owning_line` |
| Webhook routes only configured providers; `cash` 404 | DONE | `webhooks.py:104-111` | `test_an_unconfigured_provider_is_404_and_touches_nothing[cash/unknown/stripe]` (P8 red) |
| Webhook to `/payments/mock` in production → 404 (plan: "a test-only stub online provider") | PARTIAL | boot refusal `test_payment_startup.py` | No route-level test with a stub provider; guaranteed today because the API refuses to boot with the mock in production (`test_a_forbidden_configuration_refuses_to_start[production-mock-*]`) |
| An event whose provider differs from its payment's provider is stored and ignored (FR-07) | **PARTIAL** | `webhooks.py:35-36` | **None** (P6 survives): A-02 |
| A callback is never proof; verification asks the payment's own adapter | DONE | `verification.py:97-138` | `test_the_webhook_body_is_never_trusted`, `test_a_webhook_claiming_paid_captures_nothing_while_the_provider_says_pending`, `test_a_forged_signature_is_refused_and_never_stored` |
| Paid only on an exact USD amount on a live attempt of an uncancelled order | DONE | `outcome.py:38-72` | `test_outcome.py` (10 tests), `test_a_capture_that_does_not_match_exactly_is_a_late_capture` (P1, P2, P3 red) |
| Duplicate webhook applies once | DONE | `webhook_events.py:26-33`; `decide` NOOP | `test_a_replayed_event_is_stored_once_and_applied_once`, `test_a_duplicate_webhook_delivered_in_parallel_is_stored_and_paid_once` (P10 red) |
| ADR-024 lock order (orders, lines by id, payments) | DONE | `apply.py:49-50`; `public.py:78-84` | `test_payment_lock_order.py`, `test_paid_writes_the_answers_amount_after_the_three_locks` (P5, P15 red) |
| STL lines → `awaiting_delivery` atomically with verification (INV-05); emails/notifications in the same transaction | DONE | `public.py:115-153`; `ordering_side.py:28-121` | `test_a_paid_answer_marks_the_payment_and_moves_the_stl_line`, e2e `test_a_customer_buys_an_stl_and_owns_it_once_the_payment_is_verified` |
| `derive_order_status`: every branch, the only writer | DONE | `order_status.py:35-53`; `public.py:87-112` | `tests/unit/ordering/test_order_status.py`; `test_order_item_writers.py` |
| Ownership check `GET /me/stl-ownership` | DONE | `ownership.py` | `test_stl_ownership_api.py` (5 tests) |
| Checkout 30 per user per hour, fail closed; a replay counts (`api-endpoints.md:369`) | **PARTIAL** | `api/checkout.py:102-112, 256`; `limits.py:36` | Only the constant is pinned (`test_limits.py:40`). No request-level test: K9 survives (A-04) |
| Boot refuses `mock` in production | DONE | payments factory | `test_a_forbidden_configuration_refuses_to_start` |
| `purge_expired_idempotency_records` daily | DONE (code) / PARTIAL (test) | `jobs/purge_idempotency.py`; `registry.py:60` | Store-level `test_the_purge_deletes_only_expired_claims`; the job function and its registration: **none** (J1, J2 survive; `grep -rln purge_expired_idempotency_records tests` finds nothing): A-03 |
| **Done when**: `paid` only through verification; one checkout per key; paid STL `awaiting_delivery` | DONE | as above | `ck_payments_paid_verified`; K8; e2e |

### VS-024 payment recovery

| Requirement | Status | Code | Test (and mutation) |
|---|---|---|---|
| Retry on the same order for the snapshot total; owner only; `pending_payment` and uncancelled | DONE | `retry.py:39-89`; `payment_recovery.py:70-81` | `test_a_failed_attempt_is_retried_on_the_same_order_and_then_paid`, `test_the_amount_is_the_orders_total_whatever_the_product_now_costs`, `test_another_users_order_and_an_unknown_one_get_the_same_404` (T1, T3 red) |
| Retry locks `orders` first and re-checks under it | DONE | `orders.py:191-200` | `test_retry_locks_its_claim_then_the_callers_order_and_nothing_else` (T4 red) |
| Never two live attempts (index + 409) | DONE | `payments.py:263-279` | `test_retry_against_retry_opens_one_attempt` (+50-run variant), `test_the_one_live_index_race_is_a_clean_409_and_leaves_no_claim` (T6 red) |
| Retry after the hold → 409 `INVALID_STATE_TRANSITION`; boundary exact | DONE | `payment_recovery.py:80` | `test_the_hold_boundary_allows_a_second_before_and_refuses_at_it` (T2 red) |
| Retry naming an unconfigured provider → 422; kill switch never blocks retry | DONE | `checkout_rules.py:162-175` | `test_an_unconfigured_provider_and_no_provider_at_all`; docstring of the test at `test_payment_retry_api.py:109` |
| Retry racing the hold release | DONE | | `test_retry_against_the_release_job` (+50-run variant), `meet_or_fail` |
| Reconciliation: missed callback recovered in one run; outside any lock; races with webhook apply once | DONE | `reconcile.py:72-170` | `test_a_missed_callback_is_applied_in_one_run`, `test_a_hanging_query_is_cut_with_no_transaction_open`, `test_reconcile_against_webhook_applies_once` |
| Release only on an explicit `failed`/`expired`; skips on errors, unprocessed events, no status API | DONE | `domain/release.py:40-82`; `infrastructure/release.py:89-264` | `test_release_rules.py`, `test_no_explicit_answer_never_releases`, `test_an_unprocessed_event_skips_the_order_without_asking`, `test_an_open_breaker_stops_asking_and_never_releases` (R1, R3, R4, R5, R6 red) |
| Release cancels all lines (physical ones are `pending`, BR-148) and recomputes status | DONE | `public.py:161-211` | `test_physical_lines_are_cancelled_with_the_stl`, `test_only_an_unpaid_uncancelled_online_order_is_released` (R10 red) |
| Hold expiring while a payment verifies: never both | DONE | | `test_a_release_and_a_paid_answer_never_both_win`, `test_manual_release_against_a_paid_answer` |
| Manual confirm: no-status providers only; differing amount or currency 422, writes nothing; late capture on a dead attempt or cancelled order | DONE | `domain/manual.py:16-31`; `infrastructure/manual.py:31-102` | `test_a_differing_amount_is_422_and_writes_nothing`, `test_a_status_provider_is_never_confirmed_by_hand`, `test_confirm_after_manual_release_records_late_capture_not_payment` (P11–P14 red) |
| Manual release after hold + 24 h (ADR-036 d8), events reviewed, audited | DONE | `infrastructure/release.py:275-354` | `test_manual_recovery.py` (12 tests), `test_admin_payment_routes.py` (R7, R8, R9 red) |
| Late capture: `late_captured_at`, alert, lines untouched, recorded once | DONE | `apply.py:152-207`; `outcome.py:62-63` | `test_release_money_risk.py` (8 tests), `test_two_late_captures_at_once_alert_each_admin_exactly_once` (P4 red) |
| Under- and over-payment on a live attempt never applied | DONE | `outcome.py:56-61` | `test_mismatch_via_verification_is_late_capture`, `test_a_mismatched_capture_is_never_applied` |
| Admin boundary on `/admin/payments*`; rate limits | DONE | `admin_payments.py` | `test_customers_admins_without_mfa_and_csrf_less_writes_are_refused`, `test_the_sixty_first_reconcile_in_an_hour_is_429` |
| **Done when**: retry, never two live attempts; cancelled only when the hold ends unpaid; no payment stuck without an alert | DONE | | the above plus `test_stuck_is_raised_once_a_day`, `test_a_no_status_provider_is_never_released_and_release_due_is_raised_once` |

### VS-041 offer checkout

| Requirement | Status | Code | Test (and mutation) |
|---|---|---|---|
| Price only from the agreed amount; list price ignored (BR-085) | DONE | `offer_checkout.py:46-130, 142-156` | `test_checkout_charges_the_agreed_price_whatever_the_list_price` (O8 red) |
| 410 `OFFER_CHECKOUT_EXPIRED` after the window, boundary exact (BR-086) | DONE | `offers.py:334-357` | `test_the_window_closes_at_its_deadline`, `test_a_checkout_expired_offer_is_410` (O9 red) |
| Kill switch 503 (ADR-035) | DONE | `offer_checkout.py:62-63` | `test_a_paused_shop_is_503_and_writes_nothing`, `test_a_window_lapsed_while_paused_is_410_not_503` (O4 red) |
| A second checkout while a payment is live → 409 | DONE | `offer_checkout.py:70-73` | `test_a_second_checkout_while_a_payment_is_live_is_409_payment_already_active` (O5 red) |
| An offer pays for at most one line (`uq_order_items_offer_once`) | DONE | `d5507ee63176:16-22` | `test_offer_checkout_schema.py::test_a_second_line_for_one_offer_is_refused` (O3 red) |
| Order inserted before the offer lock; re-check under the lock | DONE | `offer_checkout.py:111-113` | `test_the_window_closing_while_offer_checkout_places_its_order` (O2 red; O1 equivalent) |
| Payment marks the offer `paid`; any other route auto-closes (BR-088) | DONE | `settle_offers.py:27-78`; `ordering_side.py:46-53` | `test_paying_the_offer_order_marks_the_offer_paid`, `test_buying_through_the_cart_auto_closes_a_live_offer`, `test_one_cart_payment_closes_the_live_offers_on_each_of_its_stls` (O6, O10, P16 red) |
| A payment in flight completes after the window closes | DONE | `expire_offers.py` in-flight check | `test_the_window_closing_while_a_payment_is_applied_ends_paid`, `test_the_job_leaves_an_offer_whose_payment_is_in_flight` |
| Offer checkout racing cart checkout → one owning line | DONE | ownership index | `test_offer_checkout_racing_cart_checkout_yields_one_owning_line` |
| Submission racing a payment never leaves a live offer on an owned STL (advisory lock, SRS §20.8) | DONE | `settle_offers.py:31-33` | `test_a_submission_racing_a_cart_payment_never_leaves_a_live_offer_on_an_owned_stl` (O7 red) |
| Retry of an offer order follows the offer window | DONE | `retry.py:67, 92-108` | `test_retry_of_an_offer_order_after_the_window_is_refused`, `test_retry_past_the_window_with_an_attempt_in_flight_resumes_it` (T5 red) |
| Shares cart checkout's 30/hour bucket (`api-endpoints.md:439`) | **PARTIAL** | `api/offer_checkout.py:134` | None: O13 survives (A-04) |
| Another customer's offer → 404 | DONE | `offer_checkout.py` → `SqlOfferStore.get(user_id=…)` | `test_another_customers_offer_and_an_unknown_one_are_404`; O11b red |
| `OrderDetail.can_retry_payment` and `hold_expires_at` (owed by VS-024) | DONE | `order_history.py:84-138` | `test_order_history_api.py:505-539`, `test_can_retry_payment_is_false_once_the_hold_ends` |
| End-to-end SRS §5.4 | DONE | | `test_negotiate_accept_pay_and_close_the_offer_as_paid` |
| **Done when**: charge at most once; a live offer never outlives ownership | DONE | | O3, O5, O6, O7 red |

## 5. Definition of Done (Phase 5)

| Checkbox | Met? | Evidence |
|---|---|---|
| Migrations reviewed, reversible, one head | Met | One head `d5507ee63176`; each of the four cycles restores all 18 objects; `test_migration_reversibility.py` passes |
| Rules in the owning context; others only through ports | Met | `test_deep_architecture.py` passes (in the unit run). Payments reaches Ordering and Negotiation only through `ordering.public` and `negotiation.public`; Ordering reaches Payments through `payments.public` and its `PaymentAttempts` port |
| Auth, verified email, 404 on foreign ids, admin boundary, CSRF, rate limits | Partly | `verified_user_short_read` (CSRF included) on checkout, retry and offer checkout; IDOR 404s tested (T3 red); admin payment boundary tested. Rate limits: cart 300, retry 10 and reconcile 60 per hour are tested; **checkout's 30 per hour is not** (A-04) |
| Money in integer cents; UTC; server computes every price and status | Met | BIGINT cents with CHECKs; `timestamptz` everywhere; K7, O8, P1 red; `derive_order_status` is the only writer (`test_order_item_writers.py`) |
| Audit, notification and outbox in the same transaction | Met | `payment_confirmed` and `checkout_released` write the outbox and notification on the payment's session; P14 and R9 show the audit writes are guarded |
| Every background job registered, idempotent and tested | Partly | `verify_payments`, `reconcile_payments`, `release_stale_checkouts` and `expire_offers` are registered and tested (`test_the_recovery_jobs_are_registered_with_their_cadence`, `test_expire_offers_job.py`). **The idempotency purge job has no test** (A-03) |
| Unit + PG integration + API error/IDOR + a concurrency test per known race | Met | 10 race files, 242 tests, all on `meet_or_fail`; the one `suppress(TimeoutError)` (`test_payment_recovery_races.py:88`) is a hold-open wait after the barrier, not the barrier |
| Each "Done when" covered; ruff, mypy, pytest green in CI | Met | §4; CI run 39503985134 green |
| Docs and OpenAPI updated; Status Done | Met | `cart.md`, `checkout.md`, `payment-recovery.md`, `offers.md`; `api-endpoints.md:369, 409, 439, 594-597, 695` describe the as-built routes; per-route `responses` list the 409/410/422/502/503 codes; all four slices are Done in the plan |

Test-strength checks: no money-path test uses `caplog` (so the deep-test report's weakness 2 does not apply); the alert race asserts per-admin rows, not log lines. Timing claims ("no transaction open while the provider is asked") are proved by deterministic instrumentation (`test_no_transaction_is_open_while_the_provider_creates_the_payment`, `test_checkout_no_open_transaction.py`), not wall-clock.

## 6. Findings

| ID | Sev | Location | What is wrong | Why it matters | Suggested fix (not applied) | Slice |
|---|---|---|---|---|---|---|
| A-01 | Major | `src/app/ordering/application/services/checkout.py:98-99`; `docs/checkout.md:44` | The `zero_total` refusal has no test. Deleting it (K6) leaves all checkout tests green, and so does the full money-path union plus negotiation (K6x: 1626 passed). `ck_products_price_non_negative` allows a 0 price, and `grep -rn zero_total tests` finds nothing | A regression would let a customer check out a free STL: an order with `total_cents = 0`, a $0 `pending` payment sent to the provider and, once "paid", an owned STL, while the plan (Q8) says free STLs are refused until decided | An HTTP test: a 0-priced listed STL in the cart → 422 `PAYMENT_METHOD_NOT_ALLOWED` with `reason: zero_total`, no order, no payment, cart intact. A unit test of `place_order` with fakes as well | VS-023 |
| A-02 | Minor | `src/app/payments/application/services/webhooks.py:35-36` | The FR-07 negative case "an event whose provider differs from its payment's provider is stored and ignored" has no test, although the VS-023 plan lists it. Deleting the check (P6) leaves all payment tests green (P6x on the full union: 1626 passed) | Money-safe today: verification still asks the adapter on the payment row (`verification.py:107-121`). But the event is then linked and verified instead of being stored as `provider_mismatch`, and once VS-029 creates `cash` payments, an event naming one would be left unprocessed and retried every minute (no `cash` adapter answers). VS-032's second online provider makes the mismatch reachable in production | A test that sends a signed mock event naming a `cash` payment (seeded as in `test_order_payment_schema.py`) and asserts `processing_error = 'provider_mismatch'`, `processed_at` set, no verification task | VS-023 |
| A-03 | Minor | `src/app/jobs/purge_idempotency.py:17-36`; `src/app/jobs/registry.py:60` | No test imports the daily idempotency purge job. Unregistering its cron (J2) or making its loop never stop on a short batch (J1) leaves every test green. Only the store method `purge_expired` is tested | If the registration is lost, `idempotency_records` grows without bound and a key reused after its TTL keeps replaying or conflicting instead of starting fresh. If the loop breaks, every run deletes up to 50 batches and logs a false `idempotency_purge_truncated` | A unit test that the registry holds `purge_expired_idempotency_records` at 03:53 (as `test_the_recovery_jobs_are_registered_with_their_cadence` does for the recovery jobs), and an integration test that seeds expired and live claims, runs the job with a small `batch_size` and asserts `deleted`, `truncated` and the rows left | VS-023 |
| A-04 | Minor | `src/app/ordering/api/checkout.py:102-112, 256`; `src/app/ordering/api/offer_checkout.py:134` | No test sends a 31st checkout. Removing the rate-limit dependency from cart checkout (K9) or offer checkout (O13) leaves all 880 checkout and offer target tests green. No test drives either route to 429: the money-path 429 tests cover the cart, retry, admin reconcile and the webhook, never checkout. Only the constant `CHECKOUT_RATE_LIMIT = 30` is pinned | The limit is the only brake on a customer (or a stolen session) creating orders and provider payment sessions in a loop. Its siblings are tested (`test_the_rate_limit_is_per_user_and_reads_are_never_limited`, `test_the_eleventh_retry_in_an_hour_is_429_and_redis_down_fails_closed`) | Mirror the retry test: 30 checkouts succeed or refuse normally, the 31st is 429 with `Retry-After`, and Redis down fails closed. Add one offer-checkout call to prove the bucket is shared | VS-023 (VS-041 for the offer route) |

**Follow-up: closed by branch `fix/money-audit-tests` (tests only, no application change).** Each new test was proved by re-breaking its guard on a scratch copy and watching it fail:
- A-01: `test_a_zero_total_is_422_zero_total_and_writes_nothing`. Offer checkout cannot reach a zero total, because `ck_offers_money` refuses `agreed_amount_cents = 0`; the existing `test_offer_schema.py::test_check_constraints` fails when that clause is removed.
- A-02: `test_an_event_naming_another_providers_payment_is_stored_as_provider_mismatch`, and the plan's missing `test_in_production_a_webhook_to_the_mock_is_404_and_stores_nothing` (a test-only stub provider), which answers Q-3.
- A-03: `test_the_idempotency_purge_runs_daily_at_03_53` and `test_the_purge_job_deletes_expired_claims_in_batches`.
- A-04: `test_the_thirty_first_checkout_in_an_hour_is_429_and_redis_down_fails_closed` and `test_the_thirty_first_offer_checkout_in_an_hour_is_429_shared_with_the_cart`.

**Also checked, no issue found.**
- **R2 and O1 are equivalent mutations** (see the notes in the mutation table). The re-checks are redundant, so their survival is not a gap.
- **O12, the offer-once translation, is unreachable through the API today.** A second line for one offer while the first is still `pending` also violates `uq_order_items_stl_ownership`, and PostgreSQL reports that index (`test_a_second_checkout_after_a_failed_attempt_is_409_product_already_owned` stays green under O12). Once the first line is paid or refunded, the offer is `paid` and refused before any insert. The branch is defensive dead code until VS-030 or a future writer makes it reachable.
- **Idempotency and the two-transaction checkout.** A refusal raised inside Tx1 rolls back the claim with everything else, so a retry with the same key is a fresh request. Only the 201 and the post-commit 502 are stored. A crash between the transactions leaves the claim `in_progress` naming the order, and the attempt is a reconciliation candidate (`test_checkout_crash_window.py`, `test_the_checkout_crash_attempt_gets_its_reference_and_its_result`).
- **The retry hold.** It is measured from `placed_at` (T1 in `payment_recovery.py:80`), while the release deadline is measured from the latest attempt (`hold_deadline`). That is intended (ADR-036 decision 2): a retry never extends the window in which the customer may retry, and the release deadline stays under twice the hold.
- **`OrderDetail.can_retry_payment` for offer orders** reads the offer window too (`order_history.py:124-138`), so the UI does not offer a retry that the POST would refuse.

## 7. Open questions (SRS ambiguous)

- **Q-1:** `order_items.user_id` is what `uq_order_items_stl_ownership` keys on, but nothing in the database ties it to `orders.user_id`. The only writer copies `order.user_id` (`orders.py:106`). Offer lines are already tied to their offer's customer by `fk_order_items_offer_owner`; cart lines are not. A composite FK `(order_id, user_id) → orders (id, user_id)` would make the ownership index provably about the buyer. The SRS and database-design do not ask for it. Is it wanted before VS-030 adds refund writers?
- **Q-2:** `orders.total_cents` is not tied in the database to the sum of its lines (a cross-row invariant; `database-design.md` lists only the per-row arithmetic). O8 shows the tests catch a divergence on the offer path. Should VS-030, whose refund amounts depend on line totals, add a trigger or a transactional check?
- **Q-3:** The plan's production webhook test ("ENVIRONMENT=production and a test-only stub online provider", VS-023 Tests) was replaced by the boot refusal plus `test_with_no_online_provider_every_webhook_path_is_404`. That is equivalent while `mock` is the only online adapter. Should the stub-provider test be added when VS-032 introduces a real one? (Answered: `fix/money-audit-tests` adds it now.)

## 8. How the commands were run

- Local venv `.venv` (Python 3.13.5). Static checks and the unit suite ran from the repo. The integration, concurrency, smoke, e2e, security and contract files ran in five sequential `pytest` invocations, each with its own testcontainers `postgres:16` and Redis. Docker Desktop (4 GB VM) also had the compose stack running. The full suite was not run locally, by rule; its result is CI's.
- Docker Desktop had stopped between the static checks and the first suite run, so that run errored in setup. I started it again and repeated every suite. Only the clean second run is reported.
- The migration cycle used a dedicated throwaway `postgres:16` container and the scratch copy's `alembic.ini` with `.env.example` settings, never the compose database.
- Mutations: `git archive 93268a0` into the scratchpad, with `PYTHONPATH` pointing at the copy's `src` (verified with `import app`). A driver applied one exact-match replacement at a time (dry-run asserted every pattern matched exactly once), ran the area's target tests with `-x`, recorded the result and restored the file byte-for-byte. The repo's `git status` stayed clean throughout. I briefly copied the real `.env` into the scratch copy by mistake and deleted it at once, replacing it with `.env.example`; it was never read or printed.
- The last background run (the full-union re-run of K9 and O13) was stopped by Claude Code because the machine ran critically low on memory, and was not restarted. The kill skipped the driver's restore, so the scratch `checkout.py` stayed mutated; I restored it from `git show 93268a0:…` and checked it byte for byte. No pytest process or test container was left running.
