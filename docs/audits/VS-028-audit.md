# VS-028 audit: physical checkout, delivery, pickup, payment method, dispatch estimate

Independent, read-only audit. Auditor date: 2026-11-02. Tree audited: branch `fix/vs029-audit-findings` @ `fafdcb9` (clean). Its tree is byte-identical to `main` @ `210bc9b` (#58), which was squash-merged during the audit (`git diff --quiet HEAD origin/main`). No source, test, migration or status file was changed. Mutation experiments ran only on a scratch copy (`git archive HEAD`) outside the repo.

**Update 2026-11-03:** A-01 and A-02 are fixed on branch `test/vs028-audit-fixes` with tests and docs only (§6). The first pass covered VS-049 only incidentally (M18 and its checkout test file). A light VS-049 pass has since run: 18 of 18 mutations killed (§3.1).

## 1. Verdict

**Yes.** VS-028 is a trustworthy base for the slices built on it (VS-029, VS-029b, VS-031, VS-036, VS-049, VS-050). Every "Done when" line and every test the slice plan lists has a test that runs on real PostgreSQL. Every guard that protects cash eligibility holds under mutation: the phone advisory lock, the address `FOR SHARE` lock and its owner and live filters, the block and open-order matches by account and by phone, the `>=` limit, the order of the cap and the phone lock (ADR-038 d20), the switch, the zero-total and free-line refusals, the cap boundary, phone normalisation, the stored hash, the cash-terms consent, the dispatch formula, the courier note, the amount due, the error translation, all six CHECK/unique constraints and both partial indexes, the zero-cap setting bound, and the retry/release exclusions. **All 45 mutations were killed** (two only after widening their target set, §3). I found **no Critical, Major or Minor issue**. The two findings are nits: one spelling from the plan is tested only at unit level (A-01), and the "one pure function" for the amount due is in fact three implementations that agree today (A-02).

## 2. Repo state

| Item | Finding |
|---|---|
| Current branch | `fix/vs029-audit-findings` @ `fafdcb9`, 2 commits ahead of the local `main` (`c10f80e`). Both are VS-029 audit fixes; the only `src/` change is `ordering/api/admin_cash_blocks.py` (VS-029 code). `origin/main` became `210bc9b` (#58) during the audit, with the same tree |
| Uncommitted/untracked | None at the start (`git status --short` empty). Afterwards the only new file is this report |
| VS-028 on `main`? | Yes. PR A (schema) merged as `ab3ee0c` (#27), PR B (checkout) as `2c77799` (#31), review follow-up as `0f463bd` (#32) |
| Migration | `fcd589e89e59_cash_payment_blocks_and_cash_settings.py` (revises `d5507ee63176`): `cash_payment_blocks` with its 2 partial indexes, `ck_orders_contact_phone_e164`, `ck_orders_phone_hash_format`, `ix_orders_open_cash_phone`, the three cash settings, `free_shipping_threshold` removed |
| VS-028 commits | `2b7399f`, `05f9512`, `ab4c529`, `c2fa83b`, `d3612ca`, `15c3c2f` (PR A); `9feafda`, `d96453f`, `bcf0ba5`, `80cd31c`, `675f25f`, `6acfb24`, `152a29d`, `6b2bee7`, `40248c5`, `1eef5b4` (PR B); `0f463bd` (#32) |
| Later commits touching VS-028 code | `4a5a545` (VS-029), `7649b7d` (VS-031: `SELF_CANCEL_WINDOW` in `open_order_count`, ADR-038 d23), `16ab43e` (VS-045: `accounts.is_live`), `136669c` (VS-049: `require_accepted`), `fbd5872` and `c10f80e` (VS-050: `manual` provider, `require_manual_room`) |

## 3. Command results

| Tool | Result | Notes |
|---|---|---|
| `ruff check .` | PASS | "All checks passed!" |
| `ruff format --check .` | PASS | 1019 files already formatted |
| `mypy src tests` (strict) | PASS | 869 source files, no issues |
| `pytest tests/unit` | PASS | 2499 passed, 4 warnings, 92.5 s |
| Slice integration + security batch (12 files, list in §8) | PASS | **190 passed**, 89 s |
| Slice concurrency + e2e + smoke + static batch (5 files) | PASS | **19 passed** (9 races, 2 e2e, 2 smoke, 6 lock-order/snapshot-writer static tests), 57 s |
| Full suite on the audited tree | PASS **(CI, not local)** | Run 41444681216 on `fafdcb9`: 2498 + 498 + 684 + 1176 + 674 + 636 + 593 = **6759 passed, 1 skipped, 8 deselected**, all 7 shards green |
| Full suite on `main` @ `210bc9b` (same tree) | PASS (CI) | Run 41487276770: success |
| `alembic heads` | PASS | Exactly one head: **`95ffee5fde3b`** |
| upgrade → downgrade → upgrade (throwaway `postgres:16` testcontainer) | PASS | See below |
| Committed `docs/frontend-handoff/openapi.json` vs `app.openapi()` | IDENTICAL | 120 paths; `POST /api/v1/checkout` documents 201, 400, 401, 403, 409, 422, 429, 500, 502, 503 |

**Migration probe** (`migcycle.py`, its own container): `upgrade head` → `downgrade d5507ee63176` → `upgrade head`, reading `pg_tables`, `pg_indexes`, `pg_constraint`, `settings` and `alembic_version` after each step.

| Step | `cash_payment_blocks` | Indexes (3) | Constraints (8) | Settings |
|---|---|---|---|---|
| head (`95ffee5fde3b`) | present | `ix_cash_payment_blocks_user_active`, `…_phone_active` (both `WHERE cleared_at IS NULL`), `ix_orders_open_cash_phone` (`WHERE payment_method = 'cash' AND status = 'in_progress'`) | `ck_cash_payment_blocks_{cash_only,cleared_pair,hash_format,reason}`, `ck_orders_contact_phone_e164`, `ck_orders_phone_hash_format`, `fk_cash_payment_blocks_order_payment_method`, `uq_cash_payment_blocks_order` | the three cash keys; no `free_shipping_threshold` |
| `d5507ee63176` | gone | none | none | `free_shipping_threshold` only (restored) |
| head again | present | identical definitions | all 8 | the three cash keys |

**Mutation results.** Baseline on the scratch copy, over the union of target files: **227 passed**. One mutation at a time, `-x`, the file restored after each run.

| Mutation (scratch copy only) | Result |
|---|---|
| M01 drop `cash.lock_phone(phone_hash)` | RED: `test_r1_two_accounts_one_phone_place_one_cash_order` |
| M02 drop `.with_for_update(read=True)` on the checkout address | RED: `test_r4_an_address_delete_waits_for_the_checkout_holding_it_for_share` |
| M03 drop `_LIVE` from `get_live_for_share` | RED: `test_a_deleted_foreign_or_unknown_address_is_the_same_422` |
| M04 drop the `user_id` filter from `get_live_for_share` | RED: same test |
| M05 `open_orders >= max_open` → `>` | RED: `test_a_second_open_cash_order_is_refused_by_account_and_by_phone` |
| M06 user block ignores `cleared_at` | RED: `test_blocks_match_by_account_and_by_phone_and_cleared_blocks_do_not` |
| M07 block matched by account only | RED: same test |
| M43 block matched by phone only | RED: same test |
| M08 open orders matched by account only | RED: `test_a_second_open_cash_order_is_refused_by_account_and_by_phone` |
| M44 open orders matched by phone only | RED: same test |
| M09 open count ignores `status` | RED: `test_an_order_that_is_no_longer_open_frees_the_limit` |
| M10 open count ignores `payment_method` | RED (1 of 27 in the API + exclusions files) |
| M11 cap `>` → `>=` | RED: `test_the_total_cap_is_checked_on_the_live_total` |
| M12 run `cash_precheck` after the phone lock and the limits | RED: `test_an_over_cap_total_reads_the_same_whether_or_not_the_phone_is_blocked` |
| M13 ignore `cash_payment_enabled` | RED: `test_the_cash_switch_off_refuses_and_creates_nothing` |
| M14 allow a zero total | RED: `test_a_zero_total_is_refused_for_cash` |
| M15 allow a line priced 0 (ADR-043 d12) | RED: `test_a_cart_with_a_free_physical_line_is_refused_cash_but_can_pay_online` |
| M16 drop the physical check in `cash_precheck` | RED (unit `test_fulfillment_rules.py`) |
| M17 drop the physical check in `resolve_fulfillment` | RED (unit) |
| M18 drop the STL check in `require_accepted` (VS-049) | RED (integration) |
| M19 cash terms not required | RED: `test_cash_without_the_cash_terms_is_a_validation_error_at_that_field` |
| M20 pickup phone not normalised | RED: `test_one_phone_in_four_spellings_matches_one_block_and_one_open_count` |
| M21 `contact_phone_hash` stored as NULL | RED: `test_a_second_open_cash_order_is_refused_by_account_and_by_phone` |
| M22 `cash_terms_accepted_at` not stored | RED: `test_a_cash_order_is_one_transaction_with_no_payment_and_no_provider_call` |
| M23 dispatch `ceil` → floor | RED: `test_dispatch_days` |
| M24 dispatch `max` → `min` | RED: `test_dispatch_days` |
| M25 no `delivery_fee_note` in the checkout response | RED |
| M26 no `delivery_fee_note` in the cash email | GREEN on its first targets (API file + e2e). **RED** on the wide re-run (M26b, all of `tests/integration/ordering` + the phone-leak file): `test_a_cash_order_notice_carries_no_phone_and_no_address` asserts it |
| M27 `amount_due_cents` counts cancelled lines | GREEN on its first target (the order-history test, which reads the SQL copy: A-02). **RED** on the wide re-run (M27b): unit `test_amount_due_excludes_cancelled_lines` |
| M28 `CashNotAvailableError` not translated | RED (500 instead of 422) |
| M29 drop `uq_cash_payment_blocks_order` | RED: `test_cash_payment_blocks_schema.py` |
| M30 `ck_orders_contact_phone_e164` → `true` | RED |
| M31 `ck_cash_payment_blocks_cash_only` → `true` | RED |
| M32 `ck_cash_payment_blocks_hash_format` → `true` | RED |
| M33 `ck_cash_payment_blocks_cleared_pair` → `true` | RED |
| M34 `ix_orders_open_cash_phone` not partial | RED: `test_the_partial_indexes_exist` |
| M35 `ix_cash_payment_blocks_phone_active` not partial | RED: same test |
| M36 `cash_max_order_total` minimum 1 → 0 | RED (unit `test_settings_registry.py`) |
| M37 accept `payment_provider` on a cash order | RED (`provider_not_applicable`) |
| M38 allow pickup with no `pickup_address` set | RED |
| M39 retry no longer refuses a cash order first | RED: `test_release_reconcile_retry_and_admin_release_never_select_a_cash_order` (reason `cash_order`) |
| M40 admin release no longer refuses a cash order | RED |
| M41 delivery phone not taken from the address | RED |
| M42 delivery accepts a `contact_phone` | RED (unit and API) |
| M45 cart not cleared after a cash order | RED |

45 of 45 killed. M16 and M17 are killed only by unit tests.

### 3.1 VS-049 light pass (accepted payment methods, ADR-048)

VS-049 extends VS-028's checkout. It adds the shared-method rule, `NO_COMMON_PAYMENT_METHOD`, the per-product reasons, the line snapshot and its two `order_items` CHECKs, and the `products` CHECK. Same driver and scratch copy as above, with the file restored byte-for-byte after each run. Baseline over the union of targets (`test_payment_methods.py`, `test_checkout_payment_methods.py`, `test_accepted_methods_schema.py`, `test_accepted_methods_migration.py`, `test_product_schema.py`, `test_admin_products.py`, `test_product_entity.py`, `test_cart_rules.py`, `test_cart_api.py`, `test_payment_retry_api.py`): **344 passed**.

| Mutation (scratch copy only) | Result |
|---|---|
| V01 `shared &= methods` → `\|=` (union instead of intersection) | RED: unit `test_every_combination_refuses_or_passes_as_the_rule_says` |
| V02 no `NO_COMMON_PAYMENT_METHOD` refusal | RED: `test_a_cash_only_and_an_online_only_product_must_be_ordered_separately` |
| V03 a line refusing the chosen method is not refused | RED: `test_a_method_one_product_does_not_accept_names_that_product` |
| V04 an STL accepts every method | RED: `test_an_stl_beside_a_cash_only_product_has_no_shared_method` |
| V05 cash-only accepts online too | RED: `test_a_cash_only_and_an_online_only_product_must_be_ordered_separately` |
| V06 accepted sets read before owned STLs are dropped | RED: `test_dropping_an_owned_stl_lets_a_cash_only_product_be_paid_in_cash` |
| V07 the accepted-method check moved after the price check | RED: `test_an_stl_beside_a_cash_only_product_has_no_shared_method[cash]` |
| V08 the line snapshot always `online_or_cash` | RED: `test_an_accepted_method_places_the_order_and_snapshots_the_products_value` |
| V09 `ck_order_items_method_accepted` → `true` | RED: `test_a_physical_line_cannot_snapshot_a_set_without_its_orders_method` |
| V10 `ck_order_items_accepted_methods_by_type` → `true` | RED: `test_a_physical_line_must_snapshot_what_its_product_accepted` |
| V11 `ck_products_type_integrity` lets a physical product omit the methods | RED: `test_a_physical_row_needs_every_production_field[accepted_payment_methods]` |
| V12 `ck_products_type_integrity` lets an STL carry methods | RED: `test_an_stl_row_cannot_carry_any_physical_only_field[accepted_payment_methods]` |
| V13 existing products backfilled to `online` instead of `online_or_cash` | RED: `test_stepping_back_and_forward_backfills_existing_rows` |
| V14 the create default `online` instead of `online_or_cash` | RED: unit `test_a_physical_product_created_without_accepted_methods_accepts_both` |
| V15 the domain lets an STL carry accepted methods | RED: unit `test_physical_only_fields_cover_every_required_one` |
| V16 the cart shows every method | RED: `test_the_cart_shows_the_methods_every_line_accepts` |
| V17 a cart line ignores its product's methods | RED: unit `test_a_line_carries_what_its_product_accepts` |
| V18 `NoCommonPaymentMethodError` not translated | RED (500 instead of 422) |

18 of 18 killed. BR-140 (a placed order is never re-checked) has no guard to remove, so it was not mutated; `test_a_product_turned_cash_only_after_placement_never_blocks_the_retry` passes in the baseline. This is a light pass: no migration cycle for `089f97a72014` and no requirement checklist for VS-049. "Cash requires every line physical" is checked three times (`payment_methods.py:61`, `fulfillment.py:58`, `cash.py:35`), so over HTTP only the first check can be seen. That is defence in depth, not a gap.

## 4. Requirement checklist

| Requirement | Status | Code | Test |
|---|---|---|---|
| No new order columns (they come from VS-023) | DONE | migration adds CHECKs and an index to `orders`, no column | `test_model_migration_parity.py`, `test_schema_matches_the_frozen_design` |
| Seeds `cash_payment_enabled` (true, public), `cash_max_open_orders` (1, 1–10), `cash_max_order_total` (10000 USD cents, 1–1 000 000, public) | DONE | migration `:38-60`; `settings_registry.py:169-212` | `test_the_cash_defaults_are_the_documented_ones`, `test_cash_max_open_orders_is_one_to_ten`, `test_cash_max_order_total_is_one_cent_to_ten_thousand_dollars` (M36 red), `test_public_settings.py:148` |
| `free_shipping_threshold` removed from table, registry and public allowlist | DONE | migration `:173`, restored on downgrade `:177-181` | `test_settings_seed.py:33`, `test_the_removed_free_shipping_threshold_is_not_found`, `test_free_shipping_threshold_is_gone_and_the_cash_keys_are_served`; migration probe |
| `cash_payment_blocks` table, partial indexes on `user_id` and `contact_phone_hash` `WHERE cleared_at IS NULL` | DONE | migration `:78-147` (plus cash-only composite FK, one block per order, cleared pair, hash format) | `test_cash_payment_blocks_schema.py` (each constraint refuses and is shown to be the reason; M29-M35 red) |
| `PHONE_HASH_SALT` secret, never rotated; HMAC-SHA256 of the E.164 number | DONE | `core/security.py:105-111`, `config.py`, `.env.example` | `test_phone_hash.py` (known HMAC vector), `test_phone_hash_salt_startup.py`, `test_phone_hash_salt_never_leaks.py` |
| Index for the phone lookup on unpaid cash orders | DONE | `ix_orders_open_cash_phone` (migration `:160-165`) | `test_the_partial_indexes_exist` (M34 red); reversibility test `:166-174` |
| `POST /checkout` accepts `fulfillment_method`, `address_id`, `contact_phone`, `payment_method`, `payment_provider`, note | DONE | `checkout_schemas.py:49-86` (`extra="forbid"`, no amount field) | API tests; OpenAPI identical |
| Address locked `FOR SHARE` (owner, live); deleted/foreign/unknown → one 422 `INVALID_FULFILLMENT` | DONE | `identity/infrastructure/addresses.py:100-108`; `checkout.py:151-155` | `test_a_deleted_foreign_or_unknown_address_is_the_same_422` (M03, M04 red); R4 (M02 red) |
| Phones normalised by `app.core.phone` | DONE | `checkout_schemas.py:31-38, 67-70`; `checkout.py:155` (address phone) | three-spellings test (M20 red); see A-01 |
| SRS §7.4 matrix; mismatch → 422 `INVALID_FULFILLMENT` | DONE | `fulfillment.py:28-62` | `test_fulfillment_rules.py` (5 rows × both methods, every invalid combination), `test_delivery_with_a_contact_phone_and_pickup_without_an_address_are_refused` (M42 red) |
| Snapshots: address, phone E.164 + hash, payment method, lead time, batch size | DONE | `checkout.py:199-227`; `price_lines` | `test_a_physical_delivery_online_keeps_lines_pending_and_totals_add_up`, dispatch test (snapshot `(3, 2)`), `test_snapshots_survive_later_edits_to_the_address_and_the_product`, static `test_order_snapshot_writers.py` |
| Totals recomputed (`subtotal + tax`, no shipping) | DONE | `checkout.py:162-163` | `test_totals_have_no_tax_and_no_shipping`, `test_an_order_total_equals_the_sum_of_its_lines_on_cash_and_mixed_orders` |
| Cash: physical, enabled, total > 0, no line priced 0, ≤ cap, all **before** the phone lock → 422 `PAYMENT_METHOD_NOT_ALLOWED` / `CASH_PAYMENT_LIMIT_REACHED` (`order_total`) | DONE | `cash.py:30-44`; `checkout.py:176-181` | switch, zero-total, free-line, cap, over-cap-reads-the-same and STL/mixed tests (M11-M16 red); `test_cash_is_refused_for_an_stl_only_and_a_mixed_cart_before_any_lock` asserts no `pg_advisory` statement |
| Under the cart lock and a transaction-scoped advisory lock on the phone hash | DONE | `infrastructure/cash.py:28-32`; `checkout.py:184` | R1 (M01 red), `test_each_physical_path_takes_its_locks_in_the_plan_order`, `test_place_order_locks_the_cart_then_the_address_then_the_phone`, `test_the_phone_lock_is_called_from_nowhere_else` |
| No uncleared block and fewer than `cash_max_open_orders` open cash orders, by customer **or** phone → one 422 `CASH_NOT_AVAILABLE`, no reason | DONE | `cash.py:47-50`; `infrastructure/cash.py:42-59` | `test_block_and_open_order_refusals_by_account_or_phone_are_byte_identical`, block and open-order tests (M05-M10, M43, M44 red) |
| Self-cancelled cash orders count for 24 h (ADR-038 d23, added by VS-031) | DONE (VS-031) | `infrastructure/cash.py:52-57` | `test_cash_self_cancel_window.py` (VS-031 scope, not mutated here) |
| Online with unconfigured `payment_provider` → 422 `PAYMENT_METHOD_NOT_ALLOWED`; provider stored on the payment row | DONE | `checkout_rules.py:171-184`; `checkout.py:232-239` | `test_checkout_api.py`, `test_payment_retry_api.py` (`provider_not_configured`); `payment.provider == "mock"` asserted |
| Cash order: no payment row, no provider call, status `in_progress`, cash terms recorded, confirmation email with the amount due | DONE | `checkout.py:191-198, 226, 259-260`; `notices.py:22-52` | `test_a_cash_order_is_one_transaction_with_no_payment_and_no_provider_call` (M22 red), e2e cash pickup (email `amount_due_cents`, `pickup`) |
| Every delivery response and email carries "delivery fee paid to the courier" | DONE | `fulfillment.py:18`; `checkout_schemas.py:178`, `order_schemas.py:208`, `notices.py:37`, `payments/infrastructure/ordering_side.py:91` | M25 red (response); M26b red (cash email); `test_a_mixed_delivery_order_paid_online_moves_only_the_stl_line` (online email) |
| Dispatch days = max(lead × ceil(qty ÷ batch)), from placement, both methods | DONE | `fulfillment.py:65-78`; `checkout.py:225` | `test_dispatch_days` (10 units, lead 2, batch 4 → 6), integration 5 units → 9 days (M23, M24 red) |
| Physical lines stay `pending` after online payment or cash placement | DONE | `checkout.py:230` | `test_a_physical_delivery_online_keeps_lines_pending…`, mixed-order test |
| `amount_due` (`PriceRead`, null when nothing is due) on checkout, order list and detail; tested after a cancelled line | DONE | `cash.py:53-59`; `checkout_schemas.py:192`; `order_history.py:44-50` | `test_amount_due_follows_the_live_lines_and_is_null_when_nothing_is_due`, unit `test_amount_due_excludes_cancelled_lines` (M27b red); see A-02 |

### "Tests" and "Done when" lines → tests

| Plan line | Test |
|---|---|
| Table test over all five §7.4 rows × both payment methods | `test_fulfillment_rules.py:66-137` |
| 10 units, lead 2, batch 4 → 6 days | `test_dispatch_days` |
| Cash limits: switch off, blocked customer, blocked phone on another account, second open order (same customer / other account same phone), one cent over the cap, nothing created | `test_the_cash_switch_off_refuses_and_creates_nothing`, `test_blocks_match_by_account_and_by_phone_and_cleared_blocks_do_not`, `test_a_second_open_cash_order_is_refused_by_account_and_by_phone`, `test_the_total_cap_is_checked_on_the_live_total`; each goes through `refused_cash`, which asserts no new order, payment, claim or history row and an unchanged cart |
| One phone in three spellings → one number, one hash, same block and count | unit `test_three_spellings_give_one_number_and_one_hash` (the plan's three spellings); integration `test_one_phone_in_four_spellings_matches_one_block_and_one_open_count` (bare `961…` form added after A-01) |
| Recomputed total 0 refused; setting rejects a cap of 0 | `test_a_zero_total_is_refused_for_cash`; `test_the_cash_maximum_is_never_null_and_never_zero` (M36 red) |
| Snapshot under the cap, recomputed one cent over → refused | `test_the_total_cap_is_checked_on_the_live_total` (price raised to 10001 after the cart was filled) |
| Two accounts sharing a phone in parallel, `cash_max_open_orders = 1` → one order, one 422 | R1, pickup and delivery variants (`meet_or_fail` barrier, slowed count) |
| Same `Idempotency-Key`, only `payment_method` changed → 409 `IDEMPOTENCY_KEY_CONFLICT` | `test_the_same_key_with_another_payment_method_is_409_and_a_cash_replay_is_stored` |
| Cash order never selected by release, reconciliation or retry | `test_release_reconcile_retry_and_admin_release_never_select_a_cash_order`, `test_admin_manual_release_over_http_is_409_cash_order_and_reconcile_never_selects_it` (M39, M40 red) |
| Snapshots survive later edits; phone stored normalised; no block row has a readable phone | `test_snapshots_survive_later_edits_to_the_address_and_the_product`; `test_the_sentinel_phone_and_its_hash_reach_no_response_log_or_stored_row`; `ck_cash_payment_blocks_hash_format` (M32 red) |
| Mixed order: STL `awaiting_delivery`, physical pending | `test_a_mixed_delivery_order_paid_online_moves_only_the_stl_line`, e2e mixed delivery |
| `free_shipping_threshold` gone (table, registry, public) | three tests above |
| Done when: every cart type checks out with correct totals and methods | API tests + matrix table test |
| Done when: no shipping amount; snapshots immutable | totals tests; static snapshot-writer tests |
| Done when: cash limits hold across accounts sharing a phone | R1; the byte-identical refusal test |

## 5. Definition of Done

| Checkbox | Met? | Evidence |
|---|---|---|
| Migration reviewed, reversible, one head | Met | Probe in §3; one head `95ffee5fde3b`; `test_full_downgrade_and_upgrade_round_trips` passes in CI |
| Rules in owning context; other contexts only via ports | Met | Rules are pure in `ordering/domain/{cash,fulfillment}.py`. Identity is reached only through `app.identity.public.lock_checkout_address` (`checkout_addresses.py:7`). `test_deep_architecture.py` passes in the unit run |
| Auth, verified email, 404 on foreign IDs, admin boundary, CSRF, rate limits | Met | `verified_user_short_read` and the per-user checkout rate limit (`checkout.py:127-138`), inherited from VS-023. A foreign address gets the same 422 as an unknown one (M04 red). No admin route in this slice |
| Money in cents; UTC; server computes price and status | Met | Integer cents throughout, currency fixed by ADR-008 (registry `:349`). `datetime.now(UTC)`. Status from `derive_order_status`, never assigned |
| Audit/notification/outbox in the same transaction | Met | `order.placed` audit, outbox row and notification go in Tx1 on the caller's session (`checkout.py:245-262`, `notices.py:1`). `test_a_failure_after_the_order_insert_leaves_no_order_no_claim_and_the_cart` |
| Background jobs | n/a | None added; the existing release/reconcile jobs are shown to exclude cash |
| Unit + PG integration + API error/IDOR + a race test for every known race | Met | R1-R5 (9 runs) use `meet_or_fail` or `pg_locks` waits; `_no_deadlock` guards each |
| Each "Done when" covered; ruff, mypy, pytest green in CI | Met | §4; CI runs 41444681216 and 41487276770 green |
| Docs and OpenAPI updated; Status Done | Met | `docs/checkout.md`, ADR-038 (deviations and d19-d23), `notification-contract.md:70`; committed OpenAPI identical to the app; plan Status "Done" |
| Glossary naming | Met | `Order`, `OrderItem`, `PaymentMethod`, `FulfillmentMethod`, `ProductType` kept separate; `_snapshot` suffixes; `cash_payment_blocks` |

Test strength: neither race file uses `caplog` with `configure_logging()`. Each race either meets at a barrier (`meet_or_fail`) or waits on a real `pg_locks` wait, so a race that silently ran in sequence fails. There are no timing claims.

## 6. Findings

| ID | Sev | Location | What is wrong | Why it matters | Suggested fix (not applied) | Scope |
|---|---|---|---|---|---|---|
| A-01 | Nit | `tests/integration/ordering/test_physical_checkout_api.py:582-597` | The plan's three spellings are `+961 3 123 456`, `03123456` and `9613123456`. The integration test sends `+961…`, a spaced form and `0…`, never the bare `961…` form. That form is tested only at unit level (`test_phone_hash.py:33-34`), so the path from the API schema to the phone lookup is never exercised with it | A regression in `_national_number`'s bare-`961` branch would be caught by the unit test, but not where the plan asked for it | Add `phone[1:]` (the bare `961…` form) to the spellings in the integration test | VS-028 (tests). **Fixed** on `test/vs028-audit-fixes`: the test sends four spellings and is renamed `test_one_phone_in_four_spellings_matches_one_block_and_one_open_count` |
| A-02 | Nit | `ordering/domain/cash.py:53-59`; `ordering/infrastructure/order_history.py:44-50`; `ordering/infrastructure/admin_orders.py:52-57` | ADR-038 d17 says "the amount due is one pure function". In fact there are three implementations: the pure `amount_due_cents` (checkout response, cash email, handover, cancel notices) and two identical SQL subqueries `live_total_cents` (customer order list and detail, admin queue, data export). M27 showed that the order-history test exercises only the SQL copy | They agree today. A future rule change (e.g. a new non-live line state) has to be made in three places, and each place has its own test | Build `live_total_cents` from one shared SQL expression, or amend d17 to name all three and say which test pins each | VS-028 (docs) or next change to the amount due. **Fixed** without a refactor (owner's choice): `tests/integration/ordering/test_amount_due_copies.py` checks all three over 7 cases (cash live, one cancelled, all cancelled, handed over, partly refunded, fully refunded, mixed with an STL line), and ADR-038 d17 now names the three copies and that test |

**Fix verification (2026-11-03).** The new and renamed tests pass on the branch (8 passed). On the scratch copy, with the new tests copied in, each drift they exist for is now caught:

| Mutation | Result |
|---|---|
| K1 `amount_due_cents` also drops `refunded` lines | RED: 2 of 7 cases (partly and fully refunded) |
| K2 the order-history `live_total_cents` also drops `refunded` | RED: 2 of 7 |
| K3 the admin `live_total_cents` also drops `refunded` | RED: 2 of 7 |
| K4 `_national_number` no longer recognises a bare `961` prefix | RED: `test_one_phone_in_four_spellings_matches_one_block_and_one_open_count` (the old integration test never sent that spelling) |

Also checked, no issue found: idempotency hashes the normalised body, so two spellings of one phone are one request. The address phone is E.164 by `ck_addresses_phone_e164`, so `normalise_lebanese_phone(address.phone)` cannot raise. `get_money_cents` ignores currency, but the registry refuses any currency other than USD. The free-line refusal is `CASH_NOT_AVAILABLE` but runs before the phone lock, so it reveals nothing about the phone. A paid cash order never derives `in_progress` (`test_u4_p2_a_paid_cash_order_is_never_in_progress`, `test_u5_no_edge_leaves_delivered_or_picked_up`), which keeps `open_order_count`'s reliance on `status` sound. That was the concern VS-029 must-resolve item 6 raised.

## 7. Open questions

None. The SRS (§7.4, §9.8.1, BR-037, BR-141, BR-145) and ADR-038 d19-d23 decide every behaviour I tested. The one amendment, d23's 24-hour self-cancel count, is reflected in SRS §7.3 step 9, §9.8.1 and BR-145.

## 8. How the commands were run

- Local runs used the repo's `.venv` (Python 3.13) on Windows, with Docker Desktop and testcontainers (`postgres:16`, Redis). The repo's `.env` was never read; scratch runs loaded `.env.example` into the process environment, as CI does.
- Integration batch: `test_physical_checkout_api.py`, `test_cash_order_exclusions.py`, `test_cash_checkout_lock_order.py`, `test_cash_payment_blocks_schema.py`, `test_checkout_payment_methods.py`, `test_order_history_api.py` (ordering); `test_phone_hash_salt_startup.py`; `tests/security/test_contact_phone_never_leaks.py`, `test_phone_hash_salt_never_leaks.py`; `test_admin_settings.py`, `test_public_settings.py`, `test_settings_seed.py` (platform). Second batch: `tests/concurrency/test_cash_checkout_races.py`, `tests/e2e/test_vs028_physical_checkout.py`, `tests/smoke/test_vs028_smoke.py`, `tests/unit/ordering/test_cash_lock_order.py`, `test_order_snapshot_writers.py`. Output went to files with exit codes recorded, never piped. The full suite was not run locally; its result comes from CI.
- Migration cycle: `migcycle.py` in the session scratchpad started its own `postgres:16` container and ran `alembic upgrade head`, `downgrade d5507ee63176`, `upgrade head` from the scratch copy. No dev or real database was touched.
- Mutations: `mutate.py` in the scratchpad applied one exact-string replacement at a time to a `git archive HEAD` copy (each anchor checked to match exactly once), ran its target tests with `-x` and `PYTHONPATH` pointing at the copy (confirmed: `app.__file__` resolved inside the copy), and restored the file. M26 and M27 survived their first, narrow targets and were re-run against wider sets (M26b: all of `tests/integration/ordering` plus the phone-leak file, 500 tests, 7.5 min; M27b: unit rules, the handover API, the API, exclusions and e2e files). Afterwards all 461 files under `src/` and `migrations/` in the copy were compared with `HEAD` with carriage returns ignored: no differences (the restore rewrote files with CRLF line endings).
- CI: `gh run list` / `gh run view --log` for runs 41444681216 (`fafdcb9`) and 41487276770 (`210bc9b`).
- VS-049 pass (2026-11-03): `mutate049.py`, the same method, but restoring each file byte-for-byte. V07 was built by moving the `require_accepted` block below the price check, read from the copy itself. Afterwards the copy's 461 files under `src/` and `migrations/` again matched `fafdcb9`.
- Fix verification: `killcheck.py` copied the branch's two test files into the scratch copy and ran K1 to K4 one at a time. Test names in this report are the current ones; M20 ran against the same test before its rename.
