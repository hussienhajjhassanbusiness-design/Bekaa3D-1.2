# VS-045 audit: account deletion by anonymisation

Independent, read-only audit. Auditor date: 2026-10-28. Tree audited: branch `vs-045-account-deletion` @ `05dbb8b` (clean), which is the same tree as `main` @ `16ab43e` (the squash merge of PR #51; `git diff --quiet 05dbb8b origin/main` exits 0). No source, test, migration or status file was changed. Mutations and probes ran only on `git archive` copies in the session scratchpad.

## 1. Verdict

**Yes.** The slice is a trustworthy base. **All six findings are fixed on branch `fix/vs045-audit-findings` (§9).** Every slice test, every "Done when" line and every FR-03 negative, concurrency and failure case has a test that passes on real PostgreSQL. A scan of every table for the customer's tagged personal values comes back empty. Of 41 mutations, 38 turn a test red, including every lock in the ADR-047 lock order, every re-check that makes queued requests store nothing, every scrub, and every new CHECK. No Critical or Major finding. The three survivors are small test gaps (A-01, A-02, A-05): the outbox storing a post-deletion notice as failed, the offer-checkout backstop re-check, and the order-status half of the open-order check. The behaviour itself works in each case (probed for A-01; argued in §6 for the others). The schema doc is stale (A-03), and the anonymised-order CHECK does not cover the email snapshot (A-04).

## 2. Repo state

| Item | Finding |
|---|---|
| Branch / commit | `vs-045-account-deletion` @ `05dbb8b8699a`, 6 commits ahead of the `main` it branched from (`138bad8`) |
| Uncommitted / untracked | None at the start (`git status --short` empty). Afterwards the only untracked file is this report |
| On `main`? | Yes, while the audit ran: `16ab43e` "VS-045: account deletion by anonymisation (DELETE /api/v1/me) (#51)", tree-identical to `05dbb8b` |
| Slice commits | `7b594a4` (migration `0b349a492461`), `f4d053d` (DELETE /me), `9c113c8` (review findings: phone hash, customer text, outbox, races), `ed16bff` (ADR-047 and docs), `9887011` (admin can read an anonymised account), `05dbb8b` (citext diacritic test scoped to its own token) |
| Size | 73 files, +3126 / -58 |

## 3. Command results

| Command | Result | Notes |
|---|---|---|
| `ruff check .` | PASS | "All checks passed!" |
| `ruff format --check .` | PASS | 992 files already formatted |
| `mypy src tests` (strict) | PASS | 853 source files, no issues |
| `pytest tests/unit` | PASS | 2380 passed, 84.9 s |
| VS-045 integration + smoke: `test_account_deletion.py`, `test_order_anonymised_checks.py`, `test_addresses_db.py`, `tests/smoke/test_vs045_smoke.py` | PASS | 70 passed, 57.4 s |
| VS-045 concurrency: `test_account_deletion_races.py`, `test_address_default_race.py` | PASS | 25 passed, 54.3 s |
| Existing integration suites for changed code (checkout, physical and offer checkout, receipt and its lock order, customer and admin cancel, addresses API, admin users (+ adversarial), VS-006 profile, profile, OpenAPI security, wishlist, contact messages, outbox worker, idempotency store) | PASS | 17 files, 430 passed, 4 min 48 s |
| Existing concurrency suites for changed code (`test_checkout_races`, `test_offer_checkout_races`, `test_receipt_races`, `test_wishlist_race`, `test_cash_checkout_races`) | PASS | 39 passed, 74.5 s |
| Full suite | PASS (**CI, not local**) | Run `40710543405` on `05dbb8b` (PR #51), conclusion success: unit 2379 passed + 1 skipped; integration-identity 673; integration-rest 1176; integration-payments-platform 596; integration-catalog-fulfillment 668; integration-ordering 455; concurrency-security-e2e-smoke 580. Two earlier runs on the branch failed and were fixed before merge. The `main` push run `40712674797` on `16ab43e` (same tree) also completed with success |
| `alembic heads` | PASS | Exactly one head: `0b349a492461` (revises `eeed201dcfd2`) |
| upgrade → downgrade `eeed201dcfd2` → upgrade, throwaway `postgres:16` container | PASS | At head: `orders.anonymized_at`, `addresses.anonymized_at`, `ck_orders_anonymised_shape`, `ck_orders_anonymised_closed`, `ck_addresses_required_unless_anonymised`, `ck_addresses_anonymised_shape`, and the three relaxed CHECKs (`physical_has_phone`, `delivery_address`, `phone_hash_pair` each prefixed `anonymized_at IS NOT NULL OR`); the four address columns nullable. After downgrade: both columns and four new CHECKs gone, the three CHECKs back to their original text, the four address columns `NOT NULL`. Re-upgrade: `pg_get_constraintdef` and `information_schema` output byte-identical to the first upgrade |
| Committed `docs/frontend-handoff/openapi.json` vs `app.openapi()` | PASS | Identical. `DELETE /api/v1/me`: 204, 400, 401, 403, 409, 422, 429, 500, 503; `AccountDeletionRequest` is `{current_password}` with `additionalProperties: false` |

No xfail or skip in any VS-045 test file.

**Mutation results.** Target set (14 files): the slice's unit tests (`test_anonymisation`, `test_offer_erasure`, `test_outbox_abandon`, `test_wishlist_service`, `test_address_commands`, `test_receipt_service`, `test_order_snapshot_writers`), `test_account_deletion.py`, `test_order_anonymised_checks.py`, `test_addresses_db.py`, `fulfillment/test_cancel_api.py`, `ordering/test_customer_cancel_api.py`, `test_admin_users_adversarial.py` and `test_account_deletion_races.py`. Baseline: **221 passed**. Each mutation first ran on its focused subset with `-x`; survivors were re-run on the target set plus `tests/unit/ordering`, `tests/unit/platform`, `test_offer_checkout_api.py` and `test_outbox_worker.py` (916 tests).

| Mutation (scratch copy only) | Result |
|---|---|
| M01 drop the password re-compare under the lock | RED: `test_password_changed_while_waiting_is_refused` |
| M02 / M03 / M04 skip the orders / cart / offers lock call in the command | RED: `test_success_locks_in_order_then_writes_everything_once` (unit call order) |
| M36 drop `FOR UPDATE` in `lock_orders_for_erasure` | RED: `test_deletion_racing_a_problem_report_keeps_no_personal_data[deletion_first]` (the deletion first blocks inside its `UPDATE orders`) |
| M38 empty `lock_cart_for_erasure` | RED: `test_checkout_first_makes_a_waiting_deletion_see_the_open_order` (deletion no longer sees the order; 500) |
| M39 empty `lock_live_offers_for_erasure` | RED: `test_deletion_racing_an_offer_checkout_…[checkout_first]` (500) |
| M05 `users` `FOR UPDATE` instead of `FOR NO KEY UPDATE` | RED: race suite, `deadlock detected` on `/api/v1/checkout` |
| M06 open-order check without the live-line clause | RED: `test_an_open_order_blocks_and_changes_nothing[partially_refunded_with_a_live_line]` |
| **M07 open-order check without the order-status clause** | **GREEN (survives, 916 passed)**: A-05 |
| M08 `unsettled_refund_exists` → False | RED: `test_an_unsettled_refund_blocks_and_changes_nothing[pending]` |
| M09 cart checkout skips the account re-check | RED: `test_deletion_first_leaves_a_waiting_cart_checkout_no_account` |
| **M10 offer checkout skips the account re-check** | **GREEN (survives, 916 passed)**: A-02 |
| M11 problem report skips the account re-check | RED: `test_a_report_for_an_account_deleted_meanwhile_writes_nothing` |
| M12 address lock without `anonymized_at IS NULL` | RED, but only through the race test's SQL-text wait pattern. M12b (same mutation, wait pattern loosened; the loosened pattern passes on unmutated code): RED on the outcome itself, `(201, 1, 1)`: an address with a phone stored after deletion |
| M13 order keeps the real `customer_email_snapshot` | RED: PII scan |
| M14 customer cancel note kept | RED: PII scan |
| M15 pending outbox rows not abandoned | RED: PII scan |
| **M16 outbox stores a later `.invalid` notice as pending** | **GREEN (survives, 916 passed)**: A-01 |
| M17 idempotency records kept | RED: PII scan |
| M18 tokens not spent | RED: unit call log (and the integration token assertions) |
| M19 sessions not revoked | RED: unit call log |
| M20 `auth_epoch` not advanced | RED: `test_anonymise_strips_the_login_and_voids_credentials` |
| M21 rate limit removed | RED: `test_the_sixth_attempt_in_an_hour_is_rate_limited` |
| M22 administrators allowed | RED: `test_only_an_administrator_is_blocked_by_role` |
| M23 accepted offers not withdrawn | RED: `test_addresses_wishlist_offers_messages_and_mail_are_closed_out` |
| M24 wishlist counters not decremented | RED: `test_erase_moves_each_counter_down_once_in_product_id_order` |
| M25 migration without `ck_orders_anonymised_closed` | RED: `test_the_database_refuses_a_half_anonymised_order[an_open_order]` |
| M26 migration without `ck_addresses_anonymised_shape` | RED: `test_an_anonymised_address_must_be_deleted_and_hold_no_personal_field` |
| M27 order shape CHECK allows `customer_note` | RED: `…half_anonymised_order[keeps_the_note]` |
| M28 wrong audit action | RED: unit |
| M29 cancel audit stores the note text again | RED: `test_cancel_api.py` |
| M30 contact messages kept | RED: PII scan |
| M31 auth cookies not cleared | RED: `test_the_user_row_is_anonymised_and_its_credentials_void` |
| M32 already-deleted addresses not scrubbed | RED: PII scan |
| M33 cart not emptied | RED: `test_addresses_wishlist_offers_messages_and_mail_are_closed_out` |
| M34 `users.email` not rewritten | RED: PII scan |
| M35 a waiter on an already-anonymised account proceeds | RED: `test_account_anonymised_while_waiting_is_refused` |
| M37 customer offer-round messages kept | RED: PII scan |

**Probes** (second scratch copy, not committed). (1) After deletion, an MFA administrator gets 200 from the order detail, order list, offer detail, contact-message detail and chargebacks routes for the anonymised records. (2) After deletion, an admin refund queues a customer notice (outbox rows 2 → 3) and none of the user's rows is `pending`. So the `.invalid` branch behaves as documented; it is just untested (M16).

## 4. Requirement checklist

Sources: slice section in `docs/vertical-slice-plan.md`; SRS §14.5, BR-125, BR-126, F-035; FR-03 (functional-requirements.md); entities-and-business-rules.md (User: `VERIFIED → ANONYMIZED`); api-endpoints §9.1; ADR-047.

| Requirement | Status | Code | Test |
|---|---|---|---|
| `DELETE /api/v1/me`, current password as fresh auth, `{current_password}` only (ADR-047 d1) | DONE | `identity/api/profile.py:68-125`, `schemas.py:77-82` | `test_a_wrong_password_is_401_and_changes_nothing`; OpenAPI identical |
| Wrong password 401 `INVALID_CREDENTIALS`, no change | DONE | `delete_account.py:66-67` | `test_a_wrong_password_is_401_and_changes_nothing` (all-or-nothing check `_untouched`) |
| Password re-compared under the user lock | DONE | `delete_account.py:78-79` | `test_password_changed_while_waiting_is_refused` (unit; M01 red) |
| Argon2 runs before any lock | DONE | `delete_account.py:66-70` | `test_wrong_password_takes_no_lock` (call log is `["get_by_id"]`) |
| Administrator refused, `reason: administrator` | DONE | `domain/anonymisation.py:25-27`, `delete_account.py:68-69` | `test_an_administrator_is_refused`, `test_administrator_is_refused_before_any_lock` |
| CSRF, verified email, anonymous 401 | DONE | `profile.py:72` (`require_csrf`), `current_verified_user` | `test_anonymous_unverified_and_missing_csrf_are_refused` |
| 5 attempts an hour per user | DONE | `profile.py:55-65` | `test_the_sixth_attempt_in_an_hour_is_rate_limited` |
| BR-126: open order blocks (409 `open_order`) | DONE | `ordering/infrastructure/erasure.py:29-35` | `test_an_open_order_blocks_and_changes_nothing` ×5 (pending_payment, cash in_progress, partially_refunded with a live line, returned line, STL awaiting delivery) |
| BR-126: unsettled refund blocks (409 `unsettled_refund`) | DONE | `payments/infrastructure/reports.py:142-150` | `test_an_unsettled_refund_blocks_and_changes_nothing` ×3; settled/voided/reissued do not block (`test_a_settled_or_voided_refund_does_not_block` ×3, `test_a_reissued_failed_refund_does_not_block`) |
| FR-03 concurrency: lock or re-check eligibility before anonymising | DONE | lock order `delete_account.py:72-85`; re-checks `checkout.py:110`, `offer_checkout.py:117`, `receipt.py:61`, `addresses.py:71-81` | race file, both orders each: cart checkout, offer checkout, problem report, address create, admin refund (10 tests) |
| Slice test: deletion racing a checkout never leaves an anonymised user with a new order | DONE | `checkout.py:110` | `test_deletion_first_leaves_a_waiting_cart_checkout_no_account` (M09 red), `test_checkout_first_makes_a_waiting_deletion_see_the_open_order` |
| Email becomes `deleted+<id>@invalid` | DONE | `anonymisation.py:20-22`, `repositories.py:412-419` | `test_the_user_row_is_anonymised_and_its_credentials_void` |
| Login disabled; old credentials fail; `auth_epoch` +1; sessions revoked; tokens spent | DONE | `entities.py:102-110`, `delete_account.py:91-97` | `test_the_old_credentials_and_tokens_no_longer_work` (old access token 401, refresh 401, login 401), `test_the_user_row_is_anonymised_and_its_credentials_void` |
| Cookies cleared on 204 | DONE | `profile.py:125` | `test_the_user_row_is_anonymised_and_its_credentials_void` (`access_token` not in jar) |
| Done when: the email can be registered again | DONE | partial `ix_users_email_live` + rewritten email | `test_the_email_can_be_registered_again` |
| Order snapshots lose every personal field; governorate, `admin_note`, phone hash stay | DONE | `erasure.py:38-64`; CHECK `ck_orders_anonymised_shape` | `test_financial_and_delivery_records_remain_without_personal_data`, `test_order_anonymised_checks.py` (5 refusals + 1 accept) |
| Anonymised order must be closed | DONE | `ck_orders_anonymised_closed` | `test_the_database_refuses_a_half_anonymised_order[an_open_order]` |
| Addresses scrubbed and soft-deleted (deleted ones too) | DONE | `addresses.py:143-163`; two address CHECKs | `test_addresses_wishlist_offers_messages_and_mail_are_closed_out`; `test_addresses_db.py` (3 new tests) |
| Wishlist soft-deleted, counters down once | DONE | `wishlist.py:43-49`, `infrastructure/wishlist.py:78-86` | same integration test (`wishlist_count == 0`); `test_wishlist_service.py` |
| Live offers withdrawn (accepted too), `system` round, no notification | DONE | `erase_offers.py:15-24`, `domain/offers.py:334-343` | `test_every_live_status_is_withdrawn_by_the_system`, `test_a_closed_offer_is_refused`, integration (last round `system/withdrawn`) |
| Customer offer-round messages and cancel notes nulled; admin text kept | DONE | `negotiation/infrastructure/offers.py:270-283`, `erasure.py:67-78` | `test_admin_text_survives_while_the_customers_is_gone`, PII scan |
| Contact messages anonymised | DONE | `contact_messages.py:36-51` | integration test above |
| Outbox: pending rows abandoned and redacted; every row re-addressed | DONE | `platform/infrastructure/repositories.py:100-117` | integration test above; `test_abandon_fails_the_row_and_redacts_its_payload` |
| Outbox: a later notice to a `.invalid` address stored as failed | PARTIAL (DONE after §9) | `repositories.py:61-64` | Only `is_undeliverable` is unit-tested; the repository branch is not (M16 survives; probe shows it works): A-01 |
| Idempotency records deleted | DONE | `idempotency.py:30-33` | `test_admin_text_survives_while_the_customers_is_gone` (`claims == 0`), PII scan |
| Cart emptied | DONE | `erasure.py:41-43` | integration (`cart_items` count 0) |
| Reviews keep text, no author shown | DONE | nothing written (ADR-044 shows no author) | `test_reviews_keep_their_text_and_show_no_author` |
| One audit row `user.anonymized`, counts only | DONE | `delete_account.py:99-108` | `test_one_audit_row_with_counts_and_no_personal_data`; unit `test_success_locks_in_order_then_writes_everything_once` |
| Slice test / BR-125: orders, payments, refunds, delivery records remain without PII | DONE | — | `test_payments_refunds_and_lines_are_unchanged_column_by_column` (row text identical before/after), `test_financial_and_delivery_records_remain_without_personal_data`, `test_deletion_strips_every_personal_value_from_every_table` |
| FR-03 negative: financial and audit history not physically deleted | DONE | only `idempotency_records` are deleted (retention-managed, ADR-047 d4) | column-by-column test above |
| Slice test / FR-03 failure / Done when: all-or-nothing | DONE | one request transaction | `test_a_failure_midway_rolls_everything_back` ×4 (outbox, contact messages, session revoke, audit) |
| Cash hold survives deletion (ADR-038 d23) | DONE | phone hash kept | `test_the_cash_hold_on_a_self_cancelled_phone_survives_deletion` |
| Money paths still work on an anonymised order | DONE | relaxed CHECKs | `test_an_admin_refund_on_an_anonymised_order_still_works`; race `refund_first`/`deletion_first` |
| Admin can list and read an anonymised user | DONE | `schemas.py:248` (`email: str`) | `test_an_administrator_can_still_list_and_read_an_anonymised_account` |
| Admin can read the anonymised order, offer and contact message | DONE (probe) / no test | nullable admin schemas | Probe only (§3): order detail, order list, offer detail, message detail, chargebacks all 200. Not a finding: nothing in the slice changed those schemas |
| Cancel audits `has_note`, never the text | DONE | `cancel_lines.py:189` | `test_cancel_api.py` (M29 red) |
| Offer checkout refuses an account deleted meanwhile (d7 backstop) | PARTIAL (DONE after §9) | `offer_checkout.py:117` | None: M10 survives. The withdrawn offer refuses first (`…offer_checkout…[deletion_first]` asserts 409 `withdrawn`): A-02 |

## 5. Definition of Done

| Item | Met? | Evidence |
|---|---|---|
| Migration reviewed, reversible, one head | Met | One head `0b349a492461`; down/up cycle above. The downgrade fails once an anonymised row exists, which ADR-047 states (data is gone for good) |
| Rules in the owning context; others only via ports | Met | Identity's `AccountErasure` port (`ports.py:208-222`) is implemented by `account_erasure.py`, which imports only `app.<context>.public`. `tests/unit/test_deep_architecture.py` passes in the unit run |
| Auth, verified, ownership, admin boundary, CSRF, rate limit | Met | §4 rows; the route acts only on the caller's own id, so there is no IDOR surface |
| Money in cents, UTC, server computes status | Met | No money written; `datetime.now(UTC)`; `orders.status` never assigned (only `anonymized_at` and snapshots) |
| Audit / notification / outbox side effects in the same transaction | Met | All in the request's session; the four-point failure injection proves rollback |
| Background jobs | n/a | None. ADR-047 notes VS-047's outbox-failure alert must exclude `account_deleted` rows |
| Unit + PG integration + API error + race tests | Met, with gaps | Unit tests for the command, domain, offers, outbox, wishlist and receipt service; PG tests for all six new or changed CHECKs; API tests for 401/403/409/429; ten race tests (five races, both orders). Untested: the outbox `.invalid` branch (A-01), the offer-checkout re-check (A-02), the order-status clause of the open-order check (A-05) |
| Each "Done when" covered; ruff, mypy, pytest green in CI | Met | "All-or-nothing" and "email can be registered again" each have a test; CI run `40710543405` green |
| Docs and OpenAPI updated; Status Done | Partly | ADR-047, api-endpoints §9.1, slice plan, README, frontend handoff and OpenAPI are updated. `database-design.md` is not (A-03) |

Test strength: the race tests do not use `meet_or_fail`. They hold the contested row lock on a separate connection, start each racer only after `pg_stat_activity` shows the previous one waiting on it, and fail if a racer never waits (`deletion_support.py:257-279`). That proves the overlap and fixes the order, which is stronger than a barrier; I accept it. No `caplog` use. The one `sleep` is a bounded polling loop.

## 6. Findings

No Critical or Major findings.

| ID | Sev | Location | What is wrong | Why it matters | Suggested fix (not applied) | Scope |
|---|---|---|---|---|---|---|
| A-01 | Minor (**fixed**, §9) | `platform/infrastructure/repositories.py:61-64` | Nothing tests that a notice queued *after* deletion (a later refund, chargeback or order notice to `deleted+<id>@invalid`) is stored `failed` / `account_deleted` with a redacted payload. M16 (`if is_undeliverable(…)` → `if False`) leaves 916 tests green. `test_outbox_abandon.py` covers only the pure `is_undeliverable` | Without the branch, the row would sit `pending` with its payload (order details) and be handed to the email provider up to 5 times. VS-047's alert exclusion also relies on the `account_deleted` marker. A probe shows it works today | In `test_an_admin_refund_on_an_anonymised_order_still_works`, assert that the outbox rows created by the refund are `('failed', 'account_deleted')` with every payload value `REDACTED` | VS-045 (tests) |
| A-02 | Minor (**fixed**, §9) | `ordering/application/services/offer_checkout.py:117` | The offer-checkout account re-check (ADR-047 d7) has no test; M10 survives. ADR-047 calls it "a backstop no known race reaches", and the deletion-first race is refused earlier by the withdrawn offer | Untested code that exists only for safety can rot silently. The receipt service's equivalent check has a unit test (`test_a_report_for_an_account_deleted_meanwhile_writes_nothing`) | A unit test of `place_offer_order` with a fake `CustomerAccounts.is_live` → False: `CustomerAccountClosedError`, no history or attempt written | VS-045 (tests) |
| A-03 | Minor (**fixed**, §9) | `docs/requirments/database-design.md` §5.2 (lines 503-523) and the `orders` constraints (lines 1020-1035) | Not updated. §5.2 still lists `recipient_name`, `phone`, `city`, `landmark_notes` as `NOT NULL`, and neither table lists `anonymized_at`, the two `ck_addresses_*` CHECKs, `ck_orders_anonymised_shape`, `ck_orders_anonymised_closed` or the `anonymized_at IS NOT NULL OR …` relaxation. `grep anonymi` finds only the `users` column (line 474) | The design doc no longer matches the schema (the verified `\d` output in §3); the next slice touching orders or addresses would design against the old constraints | Add the columns and the "As built (VS-045, `0b349a492461`)" constraint block, as earlier slices did | VS-045 (docs) |
| A-04 | Minor (**fixed**, §9) | migration `0b349a492461:23-27`; `ordering/infrastructure/models.py` (`ck_orders_anonymised_shape`) | The shape CHECK requires the seven address, phone and note columns to be NULL but says nothing about `customer_email_snapshot`; `pg_get_constraintdef` (§3) confirms it. The database therefore accepts an anonymised order that still holds the customer's real email, against ADR-047's "require it to hold no personal field" | The application path is guarded (M13 is caught by the PII scan), so this is defence in depth only: a future writer (an import, a manual fix) could leave the email behind with `anonymized_at` set | Extend the CHECK with `AND customer_email_snapshot LIKE 'deleted+%@invalid'` (or `~ '@invalid$'`) in a follow-up migration, with a `keeps_the_email` case in `test_order_anonymised_checks.py` | VS-045 follow-up |
| A-05 | Nit (**fixed**, §9) | `ordering/infrastructure/erasure.py:34` | The `orders.status IN ('pending_payment','in_progress')` half of `open_order_exists` is untested; M07 survives. I found no reachable state where an open-status order has only terminal lines: online-unpaid orders keep `pending` lines until `cancelled_at` is set, and cash lines reach `delivered` only with the handover payment. So the mutant looks equivalent today | It is the half that matches BR-126's wording ("orders open"). If a later slice ever lets an open order hold only terminal lines, nothing would notice | A DB-seeded case: `status = 'pending_payment'` with every line `cancelled` → 409 `open_order` | VS-045 (tests) |
| A-06 | Nit (**fixed**, §9) | `tests/concurrency/test_account_deletion_races.py:123, 203, 243-244` | The `_queued` wait patterns match exact SQL text (`%anonymized_at IS NULL FOR NO KEY UPDATE%`, `%FROM orders%FOR UPDATE%`). M12 and M36 went red only because the waiting query changed, before the outcome assertion ran; M12b had to loosen the pattern to show the real failure | A harmless refactor of the lock SQL would fail these tests with a misleading "never waited" message, and a real regression is reported as a wait-pattern error | Match on the lock target (e.g. `pg_locks` on the `users` / `orders` relation for the racer's pid) instead of the query text, or keep the pattern but name the lock in the assertion message | VS-045 (tests) |

Also checked, no issue found:
- **Signed-in contact form**: `POST /contact-messages` never sets `user_id` (`contact_messages.py:70-108`), so it cannot attach personal data to the account. Problem reports, the only `user_id` writer, are re-checked (M11 red).
- **Custom requests** have no `user_id` column (ADR-030), as ADR-047 says.
- **Refund reasons** on a customer cancel are fixed strings (`delivery_side.py:204`), so no customer text survives there.
- **Audit payloads** across Identity, Ordering, Fulfillment, Negotiation and Engagement: none carries a customer email, phone, address or message, apart from cancel notes written before this slice (`"note": ctx.note`); there is no production data yet.
- **Reopening an anonymised order**: terminal line states have no outgoing edges (`line_transitions.py:36-49`), and `derive_order_status` reaches `in_progress` or `pending_payment` only with a non-terminal line or an unpaid order. So no later refund, chargeback or recompute can trip `ck_orders_anonymised_closed`.
- **Outbox row held by a worker**: deletion waits on it (`FOR UPDATE`), then READ COMMITTED re-checks `status = 'pending'`. A row the worker sent is skipped (its payload was already redacted by `mark_sent`); a row it failed back to pending is abandoned. The `sending` enum value is unused anywhere in `src`.
- **`FOR NO KEY UPDATE` on `users` while rewriting `email`**: M05 (plain `FOR UPDATE`) deadlocks in the race suite, as ADR-047 d6 says.

## 7. Open questions

- **Q-1:** SRS §14.5 says "personal data stripped", but webhook payloads (`webhook_events`) are not scrubbed. ADR-047 notes that only mock payloads exist today. Whether a real provider's payload carries payer details depends on the undecided online provider (SRS §30.4: Whish, a card gateway, or both). When that is decided, the slice that adds the adapter should state whether deletion must redact its payloads.
- **Q-2:** BR-126 blocks deletion only while orders are open or refunds unsettled; it has no time window. ADR-047 records the owner's acceptance that a card chargeback can then arrive after the delivery evidence is gone. The SRS does not say whether "unsettled" should cover the card network's chargeback window. This is an owner decision already taken, listed only because the SRS is silent.

## 8. How the commands were run

- The repo's `.venv` (Python 3.13.5) ran everything. Integration and concurrency tests use their own testcontainers (`postgres:16`, Redis); Docker Desktop 29.2.1 was running.
- The full suite was **not** run locally (this machine runs out of memory); its result is CI run `40710543405` on the audited commit.
- Migration cycle: a throwaway `postgres:16` container on port 55445, with `.env.example` exported into the environment and `DATABASE_URL` pointed at it. It was removed afterwards. No real or dev database was touched.
- Mutations: `git archive 05dbb8b` into the scratchpad, `.env.example` exported into the environment (as CI does with `cp .env.example .env`), and `PYTHONPATH=src` so the copy's code is imported. Each mutation was a single exact-match text replacement (refused unless the pattern occurs exactly once), run with `pytest -x` on its focused tests, then reverted with `git checkout -- .`. Baseline on the full target set (14 files): 221 passed. Survivors were re-run on the full target set.
- Probes ran from a second archive copy, so the mutation driver's clean-up could not delete them.

## 9. Follow-up: fixes (branch `fix/vs045-audit-findings`)

The owner asked for every finding to be fixed, plus two races the audit had not covered. Application code is unchanged; one migration was added.

| Finding | Fix | Proof |
|---|---|---|
| A-01 | `test_an_admin_refund_on_an_anonymised_order_still_works` asserts that every outbox row the refund queues goes to `deleted+<id>@invalid`, is `failed` / `account_deleted`, and has every payload value redacted | M16 now RED on that test |
| A-02 | New `test_an_offer_checkout_refuses_an_account_closed_while_it_waited`: the checkout waits on its held offer while the account is closed by hand, then gets `401 AUTH_REQUIRED` and no order | M10 now RED (`assert 201 == 401`, the order's body) |
| A-03 | `database-design.md` §5.2: the four address columns are nullable, with `anonymized_at` and both `ck_addresses_*` CHECKs; §8.3: `orders.anonymized_at`, the three relaxed CHECKs, `ck_orders_anonymised_shape` and `ck_orders_anonymised_closed`, and the email rewrite on `customer_email_snapshot` | Docs |
| A-04 | Migration `73c7f206e9f9` (revises `0b349a492461`, which is unchanged) extends `ck_orders_anonymised_shape` with `customer_email_snapshot = 'deleted+' \|\| user_id::text \|\| '@invalid'`; the model, ADR-047 d2 and the plan say so. New CHECK cases `keeps_the_email` and `another_accounts_email` | M40 (migration without the email clause) RED: `DID NOT RAISE` on `keeps_the_email`. Migration, reversibility, model-parity and constraint suites: 22 passed |
| A-05 | New case `open_status_terminal_lines` (a `pending_payment` order whose only line is `cancelled`) → 409 `open_order` | M07 now RED |
| A-06 | `wait_for_waiters` counts lock waiters in the test database instead of matching SQL text, and the race assertions check the status before reading the body (`_refused`) | M12 RED on the outcome `(201, 1, 1)`. M36 RED on the outcome `assert 204 == 409`: without the orders lock, a deletion goes through while a refund is pending. The audit could only show that through the wait pattern |
| New | `test_deletion_racing_a_cash_checkout_never_orphans_an_order` (both orders) and `test_deletion_racing_a_counter_offer_accept_leaves_the_offer_withdrawn` (both orders: the deletion withdraws the offer either way; an accept queued behind it gets 409) | Race file: 15 passed |

Mutations re-run on an archive of the fix branch: M07, M10, M12, M16, M36 and M40 are all RED, each failing on its outcome.
