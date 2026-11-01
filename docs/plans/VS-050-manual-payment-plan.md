# VS-050 — Manual Payment: Implementation Plan

**Status:** BUILT (Revision 2). Decisions in [ADR-049](../adr/ADR-049-manual-payment.md) (Accepted). Migration `941b40d285ce`.
**Date:** 2026-10-31
**Planned against alembic head:** `089f97a72014` (VS-049, #54). One head; no other branch carries a migration.
**Format:** follows [`VS-024-payment-recovery-plan.md`](VS-024-payment-recovery-plan.md). Paths are on `main` at `136669c`.

**Revision 1 (owner, 2026-10-31):** the administrator arranges payment with the customer directly (WhatsApp or phone); the website handles no payment details. Removed from the first draft: the `whish_transfer` / `omt_transfer` providers, payee settings and `payment_instructions`, the transfer-report endpoint and its columns, reference upper-casing, the `PAYMENT_PROVIDER` list and `GET /cart` `online_providers`.

**Revision 2 (owner, 2026-10-31):** every recommendation Q1-Q7 approved. Decisions taken while building, without stopping (none changes a requirement; each is in ADR-049): `manual` is recognised by name even when not configured (d1); a blank reference is none, a given one is trimmed (d5); two confirms on one reference serialise on an advisory lock, so the loser is a 409 (d5); the admin work list carries no customer contact, which stays on `GET /admin/orders/{id}` (d11); reconciliation skips `manual` without an alert (d12); `release_order_by_admin` reads the holds itself; `OrderDetail.payment.next_step` is null for a redirecting provider (the detail never carries a redirect URL). Not built from the first plan: T14 (an offer order released at the deadline), already covered for any provider by VS-041's `expire_offers` tests.

**Review fixes (2026-10-31):** srs-reviewer and money-reviewer findings acted on are rows RF1-RF6 and the SRS §23, §20.8, FR-06, FR-07 amendments. Owner decision (2026-11-01): a duplicate transfer on one attempt is an accepted V1 limitation; the administrator returns it outside the system (ADR-049 Consequences). Accepted: lowering the manual hold moves existing deadlines.

**Goal.** Production takes online orders (cart, STL and accepted-offer checkouts) with one provider, `manual`. The order waits for payment, the administrator contacts the customer and confirms with VS-024's manual confirm, paid STL lines go to `awaiting_delivery`, and physical lines become workable exactly as today. No gateway, no crypto, no outbound call.

**Reused unchanged.** `confirm_payment_manually` (`src/app/payments/infrastructure/manual.py:37`) refuses only cash, a provider with a status API and a differing amount, then goes through `apply_provider_result` → `apply_result` (STL → `awaiting_delivery`, offers closed, projection, history, `order_payment_confirmed`). Record-capture, late capture, refunds, chargebacks, `release_unpaid_order`, retry and offer checkout already work for any adapter with `supports_status_query = False`. This is proven today with a test-only stand-in (`tests/integration/payments/test_manual_recovery.py:387`).

---

## 1. Files

### Migration (one)
- `migrations/versions/<rev>_manual_payment_provider.py`, `down_revision = "089f97a72014"`:
  - `ALTER TYPE payment_provider ADD VALUE 'manual'`, inside `op.get_context().autocommit_block()`, because a new enum value cannot be used in the transaction that adds it.
  - `ck_payments_manual_never_processing`, `ix_payments_awaiting_manual` (§3).
  - Seeds the `manual_payment_hold_period` settings row (as `de1d8a23512f` seeds).
  - Downgrade drops the CHECK, the index and the settings row. PostgreSQL cannot drop an enum value, so the value stays, and the migration says so.

### Payments context
- `domain/enums.py`: `PaymentProvider.MANUAL`.
- `domain/manual.py`: `confirm_refusal` gains `REFERENCE_REQUIRED`, which refuses a missing reference for every provider except `manual`.
- `domain/release.py`: T2 gains the manual branch. With `manual` and the deadline passed it answers `RELEASE`, without asking anything; otherwise `SKIP`. Pure.
- `application/ports.py`: `CreatedPayment.provider_payment_id: str | None`.
- `infrastructure/providers/manual.py`: `ManualPaymentProvider`. `supports_status_query = False`, `accepts_webhooks = False`; `create_payment` returns `CreatedPayment(None, None)`; `query_status` and `parse_webhook` raise (never reached).
- `infrastructure/providers/factory.py`: `ADAPTERS["manual"]`, allowed in every environment; the mock rules stay unchanged.
- `infrastructure/payments.py`: `set_provider_reference` is skipped for `None`; adds the `awaiting_confirmation` list query.
- `infrastructure/release.py`: the hold is chosen by the latest attempt's provider. For `manual` at the deadline, the release marks the attempt `expired` (no actor; audit reason `manual_hold_expired`) and calls `release_unpaid_order`. Candidates are selected with the shorter of the two holds.
- `infrastructure/manual.py`: an omitted reference skips the mismatch and owner lookups and stores nothing; a given one is trimmed only.
- `api/admin_payments.py`: `provider_reference` becomes optional, with 422 `PAYMENT_REFERENCE_REQUIRED` for non-manual providers. Adds the `awaiting_confirmation` filter and reads the customer email, contact phone and `hold_expires_at` through `ordering.public`.
- `api/webhooks.py`: an adapter with `accepts_webhooks = False` gets 404, with the same body as an unconfigured provider.

### Ordering context
- `domain/payment_recovery.py`: `hold_deadline` and `retry_refusal` take the hold chosen by provider.
- `domain/customer_view.py`: `hold_expires_at` by provider; `next_step` while the latest attempt is a live `manual` one.
- `application/services/checkout.py`, `offer_checkout.py`, `retry.py`: read the manual hold for `hold_expires_at`. Q1: require a contact phone for a manual order.
- `api/checkout_schemas.py`, `api/offer_checkout.py`, `api/payment_retry.py`, `api/order_schemas.py`: the payment read gains `next_step` (`redirect` | `await_admin_contact`); `redirect_url` stays null for `manual`.
- `infrastructure/notices.py`: Q2 (placement notices).

### Platform context
- `domain/settings_registry.py`: `manual_payment_hold_period` (§3).
- `.env.example`: documents `PAYMENT_PROVIDER=manual`.

### Docs
- `docs/SRS.md`: BR-039, BR-052, BR-054, §7.3 step 10, §9.1, §9.2 (last paragraph), §9.3 (not for manual), §15.4 (settings list). §30.4 and the §30.1 note are already updated.
- `docs/requirments/domain-glossary.md`: a **Manual Payment Provider** entry; the Whish entry becomes "a channel the administrator may agree with a customer".
- `docs/requirments/database-design.md`, `api-endpoints.md`, `entities-and-business-rules.md`; `docs/settings-registry.md` (16 → 17); `docs/payment-recovery.md`; `docs/checkout.md`; `docs/notification-contract.md` (if Q2); ADR-049 → Accepted; ADR index; slice plan; README Status.

---

## 2. Traceability

Files: `S` = `tests/integration/payments/test_manual_provider_service.py`, `A` = `tests/integration/payments/test_manual_provider_api.py`, `R` = `tests/concurrency/test_manual_payment_races.py`.

| # | Requirement / case | Enforced in | Test |
|---|---|---|---|
| T1 | `PAYMENT_PROVIDER=manual` boots everywhere; mock still refused in production | infra (boot) | `tests/unit/payments/test_provider_factory.py :: test_manual_boots_in_every_environment` |
| T2 | Cart checkout: `pending_payment`, `pending` attempt, no reference, no redirect, `next_step`, `hold_expires_at` = placed + 7 d, phone stored, notices without the phone, one admin alert | app, API | `A :: test_an_stl_checkout_waits_for_the_administrators_call` |
| T2b | Q1: STL-only `manual` without a phone is 422 and writes nothing; other providers still refuse a phone | domain | `A :: test_a_manual_stl_checkout_without_a_phone_writes_nothing`; `tests/unit/ordering/test_fulfillment_rules.py :: test_a_manual_stl_only_order_takes_the_phone_to_call_and_needs_it`, `test_a_physical_order_already_has_its_phone_to_call` |
| T3 | Confirm (no reference) pays a mixed pickup order: STL `awaiting_delivery`, physical `pending` | existing `apply_result` | `A :: test_confirm_without_a_reference_pays_a_mixed_order`; `S :: test_confirm_without_a_reference_pays_and_moves_the_stl_line` |
| T4 | Offer checkout needs the phone, charges the agreed price, confirm pays it, offer `paid` | app | `A :: test_an_offer_checkout_needs_the_phone_and_is_paid_by_confirm` |
| T5 | Omitted references never collide; blank is none; given is trimmed, case kept, unique | domain + DB | `S :: test_confirm_without_a_reference_pays_and_moves_the_stl_line`, `test_a_blank_reference_is_none_and_a_given_one_is_trimmed_case_kept`; `A :: test_a_given_reference_must_be_unique_and_others_still_need_one` |
| T7 | Any other provider still needs a reference (422 `PAYMENT_REFERENCE_REQUIRED`), before the amount | domain | `tests/unit/payments/test_manual_confirm_rules.py :: test_only_manual_may_omit_the_reference`, `test_a_missing_reference_is_refused_before_the_amount`, `test_record_capture_refusals_in_order`; `S :: test_any_other_provider_still_needs_its_reference` |
| T8 | Wrong amount: 422; record-capture (no reference) is a late capture, attempt `failed`; retry gives a new `manual` attempt and alert | existing + Q4 | `A :: test_a_wrong_amount_is_refused_recorded_as_a_late_capture_and_retried` |
| T9 | Webhook to `manual` is 404, nothing stored | API | `A :: test_the_manual_provider_takes_no_webhooks` |
| T10 | Reconciliation never asks or alerts about `manual` | job | `S :: test_reconciliation_never_asks_or_alerts_about_a_manual_attempt` |
| T11 | Hold chosen by provider; retry bound at the manual deadline | domain | `tests/unit/ordering/test_payment_recovery_rules.py :: test_the_hold_is_chosen_by_the_attempt_provider`, `test_a_manual_order_may_retry_until_its_own_hold_ends` |
| T12 | Job: not due at +1 h and at deadline - 1 s, released exactly at the deadline (`expired`, cancelled, notice, audit `manual_hold_expired`, STL freed) | job | `S :: test_the_job_releases_a_manual_order_exactly_at_its_own_deadline`; `tests/unit/payments/test_release_rules.py :: test_a_manual_attempt_is_answered_by_the_platform_and_released` |
| T12b | `manual` is known by name: confirm and release work with no adapter configured | infra | `S :: test_confirm_needs_no_configured_adapter_for_manual`, `test_the_job_releases_a_manual_order_even_with_no_adapter_configured` |
| T13 | Money after release: late capture and its refund; order stays cancelled | existing | `S :: test_a_payment_after_the_release_is_a_late_capture_with_its_refund` |
| T15 | Admin list `awaiting_confirmation=true`: live `manual` only, `hold_expires_at`, no customer email | API + query | `A :: test_the_admin_work_list_holds_only_live_manual_attempts` |
| T16 | Order detail `next_step` only while waiting; `hold_expires_at` = placed + 7 d | domain view | `A :: test_the_order_detail_shows_the_next_step_only_while_waiting`; `tests/unit/ordering/test_customer_view.py :: test_a_live_manual_attempt_awaits_the_administrators_call`, `test_an_attempt_that_is_over_has_no_next_step` |
| T17 | Setting: 7 d default, 1 h - 30 d, internal; seeded | platform | `tests/unit/platform/test_settings_registry.py :: test_the_manual_hold_is_seven_days_editable_from_one_hour_to_thirty_days`; `tests/integration/platform/test_settings_seed.py` |
| T18 | DB refuses a `manual` payment in `processing`; accepts a pending one without a reference and an STL-only order with a phone; the index exists | DB | `tests/integration/ordering/test_order_payment_schema.py` (`manual-payment-processing`, `manual-payment-pending-without-reference`, `stl-only-order-with-the-phone-to-call`, `test_every_lookup_index_exists`) |
| T18b | Migration down and up | DB | `tests/integration/payments/test_manual_provider_migration.py` |
| Q3 | The administrator may release a `manual` order at once | domain + infra | `S :: test_the_administrator_may_release_a_manual_order_at_once`; `tests/unit/ordering/test_payment_recovery_rules.py :: test_a_manual_order_may_be_released_by_hand_from_placement` |
| C1 | Confirm vs the job's release at the deadline, in both orders | lock order + re-check | `R :: test_a_confirm_and_the_release_at_the_deadline_never_both_win` (`release`, `confirm`) |
| C2 | One reference typed on two payments: one paid, one 409 | reference advisory lock | `R :: test_one_reference_typed_on_two_payments_pays_one` |
| C3 | One payment confirmed twice: paid once | payment lock | `R :: test_one_payment_confirmed_twice_is_paid_once` |
| RF1 | Money review: record-capture's `manual` reference is stored and unique; reused on record-capture or confirm is 409 | infra | `A :: test_a_wrong_amount_is_refused_recorded_as_a_late_capture_and_retried` |
| RF2 | Money review: the admin alert commits with the order even if Tx2 fails | API (Tx1) | `A :: test_the_alert_commits_with_the_order_even_if_the_second_transaction_fails` |
| RF3 | Both reviews: a retry onto `manual` of an order without a phone is 422 | app | `A :: test_a_manual_retry_on_an_order_without_a_phone_is_422` |
| RF4 | SRS review: offer checkout's notices, alert and hold; another provider refuses its phone | app | `A :: test_an_offer_checkout_needs_the_phone_and_is_paid_by_confirm`, `test_another_provider_refuses_a_phone_on_an_offer_checkout` |
| RF5 | SRS review: a physical delivery order on `manual`, paid by confirm | app | `A :: test_a_physical_delivery_order_is_paid_with_the_address_phone` |
| RF6 | Money review: an admin release racing a confirm, both orders | lock order | `R :: test_an_admin_release_and_a_confirm_never_both_win` (`release`, `confirm`) |

Mutation checks run (each guard deleted, its test failed): the record-capture reference store, the retry phone check, the Tx1 alert (cart and offer), the offer's other-provider phone refusal, the reference lock, the job's manual answer, the provider-chosen hold, both phone-required checks, the webhook 404, `REFERENCE_REQUIRED`, reconcile's manual skip, the any-time manual release, the admin alert, the customer notice, reference trimming, `manual` by name. Equivalent mutant: skipping `set_provider_reference` for `None` (it would write `NULL` over `NULL`).

---

## 3. Database constraints and setting

| Invariant | Constraint |
|---|---|
| A given reference is unique per provider; omitted ones never collide | existing `uq_payments_provider_reference (provider, provider_payment_id)` (nulls distinct) |
| One live attempt per order | existing `uq_payments_one_live` |
| Paid only with a verification time | existing `ck_payments_paid_verified` |
| Nothing can put a manual attempt in `processing` (it has no provider to report it) | `ck_payments_manual_never_processing`: `provider <> 'manual' OR status <> 'processing'` |
| Admin work list | `ix_payments_awaiting_manual (initiated_at, id) WHERE provider = 'manual' AND status = 'pending'` |

| Key | Type | Default | Range | Public |
|---|---|---|---|---|
| `manual_payment_hold_period` | duration (s) | `604800` (7 d) | 3 600 – 2 592 000 (1 h – 30 d) | ❌ |

---

## 4. Order of work

One PR: migration and schema tests, then domain → application → infrastructure → API with T1-T19 and C1-C3, then docs. srs-reviewer and money-reviewer review it. This is a money slice, so you merge it.

---

## 5. Open questions (all approved as recommended, 2026-10-31)

| Q | Question | Recommendation |
|---|---|---|
| Q1 | **The administrator needs a phone to contact the customer, but an STL-only order and an accepted-offer order store none** (SRS §7.4: STL-only needs no phone; offer checkout takes none; `users` has no phone). | When the provider is `manual`, require `contact_phone` (Lebanese, E.164, as pickup does) on every online checkout, offer checkout included, and snapshot it on the order (`contact_phone_snapshot` / `_hash` already exist and are allowed with no fulfillment method). Alternative: contact by email for those orders. Needs an SRS §7.4 edit. |
| Q2 | Should the administrator get an alert for each new manual order (otherwise they must poll the list), and the customer a placement notice? | Yes to both. An admin alert `manual_payment_due`, one per order, in-app now and by email once VS-021 is built. A customer notice `order_awaiting_payment` ("placed; we will contact you to arrange payment"), in-app and email. |
| Q3 | Can the administrator release a manual order before the 7 days, once the customer says they won't pay? Today a manual release opens only 24 h after the deadline (ADR-036 d8), and the job releases first anyway. | Yes. For `manual`, `POST /admin/orders/{id}/release` is available at any time, with the mandatory reason, audited. Otherwise an abandoned STL keeps the customer's ownership index for 7 days. |
| Q4 | Record-capture's `dashboard_reference` is required. Should it be optional for `manual` too? | Yes, the same rule as confirm: optional for `manual`, unique when given. |
| Q5 | Is the reference a transfer id or a free note? It is unique when given, so writing the same note twice ("WhatsApp") would be refused as a duplicate. | Treat it as the transfer id (Whish/OMT receipt number); notes go in the mandatory `reason`. Say so in the admin UI text. |
| Q6 | Hold range | 1 h – 30 d, default 7 d; it also bounds retry for manual orders. |
| Q7 | The dispatch estimate counts from placement (§8.6), but production waits for confirmation (up to 7 days). | Keep the SRS rule. Flagged, not changed. |

**Needs an SRS change once answered:** BR-039 and §9.2 (auto-release at the manual hold), §7.3 step 10 and §9.1 (the manual provider), BR-054 (manual confirmation with an optional reference), §15.4 (the setting), and Q1 (§7.4) if accepted.

**Out of scope:** payee details or instructions on the website, a customer "I've paid" action, receipt uploads, reminders, LBP pricing, a second provider or a provider list.
