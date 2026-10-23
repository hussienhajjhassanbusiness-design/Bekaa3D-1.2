# VS-030 — Refunds and Settlement: Implementation Plan

**Status:** IN PROGRESS (PR B, branch `vs-030-refund-core`), revision 2. PR A (`vs-030-schema`,
migration `c01e53ab3e0f`) is merged as `7b346a4`. The owner answered Q1-Q12 on 2026-10-23
(Revisions 1 and 2 below).
**Date:** 2026-10-23
**Planned against alembic head:** `0f43e238eaae` (`contact_message_order_link`, VS-029b, merged
as `fc641dc` after revision 1 was written against `b6e1d0c4a2f7`).
- Re-derived statically from `revision` / `down_revision` in `migrations/versions/` at PR A's
  start: 29 revisions, one linear chain, one head. No file names `0f43e238eaae` as its
  `down_revision`; no merge revisions.
- PR A's migration (§4.2) therefore has `down_revision = "0f43e238eaae"`; PR C's data
  migration (§4.3) revises PR A's.
- Re-derive the head immediately before each later `alembic revision`.

**Pre-flight (2026-10-23):** `git fetch`, `git checkout main`, `git pull --ff-only` (already
up to date at `326aa40`). Remote branches: `docs/adr-035-accept-decisions`,
`feat/vs-038-wishlist`, `fix/money-audit-tests`, `fix/vs-028-review`,
`fix/vs-040-accept-expected-amount`, `vs-022-mixed-cart`, `vs-023-checkout`, `vs-023-schema`,
`vs-023b-stl-delivery`, `vs-024-recovery`, `vs-024-schema`, `vs-025-order-history`,
`vs-028-checkout`, `vs-028-schema`, `vs-029-admin-order-queue`,
`vs-029b-receipt-confirmation-and-problem-report`, `vs-039-offer-submission`,
`vs-040-offer-negotiation`, `vs-046-security-retention`.
- Only `origin/fix/money-audit-tests` has a commit naming VS-030 (`24bd0de`, "record the
  VS-041 audit's Q-1 and Q-2 decisions"). Its text is already on `main`
  (`docs/vertical-slice-plan.md:796`, `:806`, `:813`) and in
  `docs/audits/VS-041-audit.md:257-258`; it is a stale branch, not a VS-030 implementation.
  No branch touches refund code or schema.
- Highest ADR on `origin/main`: **ADR-041** (VS-029b, merged on 2026-10-23); no unmerged branch
  holds a higher one. This slice's ADR is **ADR-042** (re-checked at PR A's start).

**Format:** follows [`VS-024-payment-recovery-plan.md`](VS-024-payment-recovery-plan.md).
Every `file:line` below is on `main` at `326aa40`.

---

## Revision 2 (2026-10-23): PR A starts

- **No co-developer confirmation is needed for D1.** The owner works alone, so the owner's Q1
  answer is the confirmation the VS-023 note (`docs/vertical-slice-plan.md:793`) asks for.
- VS-029b merged (`fc641dc`, migration `0f43e238eaae`, ADR-041). PR A revises `0f43e238eaae`,
  and the ADR number stays 042.
- Q1-Q12 stand as recorded in Revision 1. Q8 means no phone and no hash in the cash-block
  search audit. Q6 means a non-USD late capture is stored as reported, never converted. Q12
  means the open-cash count stays status-based, with the P1 and P2 proofs.
- PR A builds §4.2 and §4.2a only. The backfill (§4.3) stays in PR C, and no application code
  reads or writes the new tables.

## Revision 1 (2026-10-23): owner answers and review changes

**Answers to §10, recorded as decided. They bind PR A to PR C.**

| Q | Decision |
|---|---|
| Q1 | Owed refund first; "all lines refunded" dropped. ADR-042 states that it **amends SRS §20.2** (and database-design §17.2). The old-versus-new comparison is in §3.1a. |
| Q2 | `voided` plus `POST /refunds/{id}/void`, refused when any of its lines is already `refunded`. |
| Q3 | A chargeback voids every pending and owed refund on its payment. |
| Q4 | Chargebacks are built in VS-030 PR C (separate tables). VS-031 is added to VS-032's dependencies. |
| Q5 | `record-capture` is built in PR C (no-status-API providers, mismatched amounts only). |
| Q6 | A late capture with no reported amount uses the attempt amount, flagged in the reason. **A non-USD captured currency is recorded as reported and never converted.** |
| Q7 | "Refund issued" at creation for `admin` and `cancellation`; for `late_capture` at settlement only; none on fail, reissue or void. |
| Q8 | The cash-block search audit records **no phone and no hash at all**: filters, result count and block ids only. |
| Q9 | The customer summary shows `admin`, `cancellation` and `late_capture` refunds as "processing" or "refunded"; voided refunds and chargebacks are hidden. |
| Q10 | `Idempotency-Key` is required on reissue and chargebacks, as well as on create and record-capture. |
| Q11 | 409 `ORDER_TOTAL_MISMATCH`, an error log and an alert; nothing written. |
| Q12 | The status-based open-cash count is kept, with the P1 and P2 proofs and tests (§3.1, U4 and U5). |

**Changes in this revision:**
1. §3.1a gains a table-driven [M] test comparing the old and new `derive_order_status` over
   every input combination, with each differing output listed and justified.
2. §2.3, §4.2, §6.2 and §6.3 make void admin-only, reason-required, audited and
   idempotent.
   - A settled refund can never be voided, and a voided refund can never be reissued (state
     rules plus a CHECK).
   - Four new real-Postgres races cover chargeback vs settle, chargeback vs reissue,
     create vs chargeback, and void vs settle.
3. §4.2 and §6.2 add the chargeback constraints `ck_chargebacks_online_only` and
   `uq_chargebacks_dispute`, each with a refused-case test asserting the constraint name.
   Production stays on `PAYMENT_PROVIDER=none` until VS-032 (§2.5).
4. §4.3 rewrites the backfill: idempotent, batched, a downgrade that deletes only rows it
   created, and malformed or unparseable audit rows skipped and reported, with a test.
5. §4.2a adds PR A's order of operations: `NOT VALID` then `VALIDATE`, the lock each step
   takes, and the precheck. PR A merges alone, before any code uses it.
6. §8.1 restates the lock-order table for all nine paths in full (plus void, the backfill
   and checkout), with the no-cycle proof.

---

## 0. Decisions this plan takes (summary)

| # | Decision | Where |
|---|---|---|
| D1 | `derive_order_status`, once a payment reached paid: **owed refund → `partially_refunded`** first, then all cancelled → `cancelled`, then coverage → `refunded`, then any refund → `partially_refunded`, then terminal → `completed`. The "all lines refunded" rule is dropped as redundant (proved in §3.1). Must-resolve 1. | §3.1, ADR-042 |
| D2 | A new terminal refund status **`voided`** (audited, admin-only, reason required). Recording a chargeback voids every pending and owed refund on that payment in the same transaction. Total payout never exceeds the money paid. Must-resolve 2. | §2.6, §3.3 |
| D3 | Chargebacks get **their own tables** (`chargebacks`, `chargeback_items`), not `refunds.kind = chargeback`. `applied_cents >= 0`, `excess_cents >= 0`, and their sum `> 0`. Must-resolve 3. | §4.2 |
| D4 | A chargeback that brings an unfinished physical line's balance to 0 **cancels that line in the same transaction** (no refund). A fully covered terminal line (or `returned`) becomes `refunded`. Must-resolve 4. | §3.3 |
| D5 | `POST /api/v1/admin/orders/{id}/chargebacks` with a **required `Idempotency-Key`** and a unique `(payment_provider, provider_dispute_reference)`. Online payments only (CHECK plus FK). VS-031 is added to VS-032's dependencies. Must-resolve 5. | §2.5, §7 |
| D6 | The open-cash count stays status-based (no new index). Both properties are **proved** and pinned by property tests over every status input and a structural edge test. Must-resolve 6. | §3.1, §6.1 |
| D7 | One global lock rank: idempotency claim → `orders` → `order_items` by id → `payments` by id → `refunds` by id → `chargebacks`, then (VS-031 only) cart → phone advisory lock. No path ever takes a lower rank after a higher one, so there is no cycle. | §8.1 |
| D8 | Balances are derived from rows read **after** the `orders` lock, inside the refund transaction. Every writer of `refunds`, `refund_items` and `chargebacks` holds that lock. Q-2 (`total_cents = Σ line_total_cents`) is asserted first. Q-1 is a composite FK. | §3.2, §4.2 |
| D9 | The `refund_present` stop-gap is replaced by real refund facts passed in by callers. The strict-xfail test is deliberately converted into a passing test. | §3.4 |
| D10 | The late-capture refund goes through the existing `LateCaptureSink` hook (`verification.py:59`): capped by `captured_amount_cents`, one live per payment (partial unique index), plus a rerunnable backfill migration with the pre-VS-024 audit fallback. | §3.5, §4.3 |
| D11 | Refunds are owned by **Payments** (tables, use cases, routes). Ordering keeps every `order_items` write and `orders.status`. Callers pass refund facts into Ordering, as they already pass `reached_paid` (`transition_line.py:61`). | §3.0 |
| D12 | No provider refund API, ever, in V1 (ADR-024 d16). The provider port gains nothing. | §1 |

---

## 1. Scope and non-goals

### In scope (VS-030 only)
- Schema: `refunds`, `refund_items`, `chargebacks`, `chargeback_items`, enums `refund_kind`
  (`admin`, `cancellation`, `late_capture`) and `refund_status` (`pending`, `settled`,
  `failed`, `voided`).
- Schema, Q-1: `uq_orders_id_user`, plus the composite FK `fk_order_items_order_owner`
  (`NOT VALID`, then validated).
- Schema, supporting keys: `uq_order_items_id_order`, `uq_payments_id_order_provider` and
  `uq_refunds_id_order`, which the composite FKs need.
- Admin refund API: create, list (obligations queue and history), get, settle, fail,
  reissue and void.
- Admin chargeback API: record, list per order and get.
- Refund creation with per-line partial amounts, per-line and per-payment balances, the Q-2
  check, BR-149 paid lines only, `REFUND_REQUIRES_CANCELLATION`, lines becoming `refunded`,
  the STL queue and ownership effects, and payment and order status recompute.
- `derive_order_status` reorder (D1), plus a payment status projection that can go back
  (`refunded → partially_refunded → paid`).
- Replacing the `status_inputs_for` stop-gap (`src/app/ordering/public.py:230-241`), with
  all three callers updated.
- The automatic `late_capture` refund through `LateCaptureSink`, its backfill, and the VS-024
  Q2 decision (§3.6).
- The "refund issued" email and in-app notification (`NotificationType.REFUND`,
  `src/app/engagement/domain/enums.py:11`).
- The customer `OrderDetail` refund summary (deferred here by ADR-033 d7), plus refunds,
  chargebacks and per-line balances in `AdminOrderDetail`.
- Auditing cash-block phone searches (`docs/vertical-slice-plan.md:817`, added by #34).
- The published interface VS-031, VS-032, VS-036, VS-043 and VS-045 consume (§3.7).

### Non-goals, and exactly who owns them
| Not here | Owner | Note |
|---|---|---|
| Cancel and return edges, self-cancel, admin cancel, cash blocks on refusal | VS-031 | VS-031 calls `create_refund(kind=cancellation, cancelling=…)` (§3.7). |
| Provider dispute webhooks, live provider adapters | VS-032 | VS-032 may call `record_chargeback` from a webhook path; the manual route is here. |
| Badge recompute hook | VS-036 | §3.7 names the hook point (after every refund or chargeback write). |
| Revenue analytics | VS-043 | §3.7 defines the "refunded money per line" read. |
| Account deletion blocking (BR-126) | VS-045 | §3.7 defines `unsettled_refund_exists(user_id)`. |
| Any provider refund API call | Never in V1 | ADR-024 d16, `docs/adr/ADR-024-…md:55`. |
| Shipping refunds | Never | ADR-024 d1, `:18`. |

---

## 2. API and jobs

Every route sits behind `AdminBoundaryRoute`, `require_admin` (MFA), and `require_csrf` on
writes. A per-administrator rate limit applies: 60/h on writes and 300/h on reads, as
constants in `app.payments.domain.limits`. The routes live in a new
`src/app/payments/api/admin_refunds.py` (refunds) and `admin_chargebacks.py`, and are
registered in `src/app/api/v1/admin.py` next to `admin_payments_router` (`:115`).
Error bodies use the existing problem format.

### 2.1 `POST /api/v1/admin/orders/{order_id}/refunds` — create (required `Idempotency-Key`)

The request is `RefundCreate` (`docs/requirments/api-endpoints.md:1139-1158`):
`{items: [{order_item_id, amount_cents > 0}] (1..50, unique ids), reason: str (1..1000)}`.
- Success is `201 RefundDetail`. A replay returns the stored 201 with `Idempotent-Replayed: true`
  (`src/app/ordering/api/idempotent.py:13-32`).
- Errors:
  - 404: no order, or a line of another order.
  - 409 `ORDER_NOT_PAID`: no payment reached paid, including an unpaid cash order.
  - 409 `IDEMPOTENCY_KEY_CONFLICT`, and 409 `IDEMPOTENCY_IN_PROGRESS`.
  - 409 `ORDER_TOTAL_MISMATCH`: the Q-2 check.
  - 422 `REFUND_EXCEEDS_AVAILABLE`, with `available` per line and for the payment.
  - 422 `REFUND_REQUIRES_CANCELLATION`, with the offending `order_item_id`s.
  - 422 `VALIDATION_ERROR`, and 429.
- It always records `kind = admin`. `requested_by = approved_by = admin`.
- **Idempotency:** scope `admin_refund_create`, `user_id = admin id`, and
  `request_hash(scope, {order_id, items sorted by id, reason})`
  (`src/app/platform/domain/idempotency.py:43-47`). The claim, the writes and `complete` run in
  **one transaction**, so a failure rolls the claim back and a retry re-executes. Only the
  201 is stored. A 4xx writes nothing and stores nothing, so the same key may retry after
  the admin corrects the request. This differs from checkout's two-transaction flow
  (`src/app/ordering/api/checkout.py:302-375`) because there is no provider call.

### 2.2 `GET /api/v1/admin/refunds` and `GET /api/v1/admin/refunds/{refund_id}`
- **List:** cursor `(created_at, id)`, plus filters `queue=true` (the default), `status`, `kind`,
  `order_id`, `customer_id` and `created_from`/`created_to`.
  - `queue=true` is exactly `status = 'pending' OR (status = 'failed' AND reissued_at IS NULL)`,
    oldest first, served by `ix_refunds_obligations`.
  - `queue=false` lists everything, newest first.
  - Chargebacks never appear: they are another table (D3).
- `RefundDetail`: id, order id and number, payment id and provider, kind, status, amount, currency,
  reason, requested_by, approved_by, the items (line id, product name snapshot, amount),
  reissue links (`reissue_of_refund_id`, `reissued_by_refund_id`), and the settlement and
  failure and void fields. It never includes a phone, a hash, an address or a provider reference.

### 2.3 `POST /api/v1/admin/refunds/{refund_id}/settle`, `…/fail`, `…/void`
- **Settle** (`RefundSettlementRequest {reference?: str ≤200, note?: str ≤1000}`): `pending →
  settled`.
  - Settling an already `settled` refund returns 200 unchanged (a double submit).
  - `failed` or `voided` gives 409 `INVALID_STATE_TRANSITION` (`reason=not_pending`).
  - **It changes no order or payment status** (ADR-024 d12).
  - The "settle" wording drops "provider-confirmed completion" (ADR-024 appendix,
    `docs/adr/ADR-024-…md:111`).
- **Fail** (`RefundFailureRequest {reason}`): `pending → failed`. A second fail returns 200
  unchanged; `settled` or `voided` gives 409. It recomputes payment and order status
  (owed → `partially_refunded`). No line changes.
- **Void** (new; `RefundVoidRequest {reason: str 1..1000}`, `extra="forbid"`; Q2):
  - **Who:** admin-only (boundary, MFA), CSRF, and the per-admin write limit.
  - **Legal sources:** `pending → voided`, or `failed` with `reissued_at IS NULL` → `voided`.
    It is the only way to close an obligation created by mistake.
  - **Refusals (409 `INVALID_STATE_TRANSITION`):**
    - `settled` → `reason=already_settled`: **a settled refund can never be voided**. The
      service checks the locked row, and the database backs it with
      `ck_refunds_void_never_settled` (§4.2).
    - `failed` with `reissued_at` set → `reason=already_reissued`.
    - Any of its lines already `refunded` → `reason=line_already_refunded`. Line states never
      revert (ADR-024 d11), and a `refunded` line has balance 0 by state (§3.2 L2).
  - **Idempotent by state:** voiding an already `voided` refund returns 200 with the stored row
    unchanged. The original `void_reason`, `voided_by` and `voided_at` are kept, and no second
    audit row is written. No `Idempotency-Key` is needed, because the second call cannot write.
  - **Effects:** it sets `voided_at`, `voided_by` and `void_reason`, frees the voided items'
    balance, recomputes payment and order status, and writes one audit row `refund.voided`
    (`before_data {status}`, `after_data {status, reason, order_id, amount_cents}`, request id,
    ip hash). There is no email (Q7).
  - **A voided refund can never be reissued:** reissue accepts only `failed`, so a voided refund
    gives 409 `reason=not_failed` (§2.4).
- All three use the same lock order (§8.1):
  1. an unlocked read of the refund to learn `order_id`;
  2. `orders` → lines → payment → the refund `FOR UPDATE`;
  3. a re-check that the refund still belongs to the order, then the decision on the locked row.

  This is the `apply_result` pattern (`src/app/payments/application/services/apply.py:46-52`).

### 2.4 `POST /api/v1/admin/refunds/{refund_id}/reissue` (required `Idempotency-Key`)
- Only for a `failed` refund with `reissued_at IS NULL`. `pending`, `settled` and **`voided`**
  give 409 `reason=not_failed`. A voided refund is never reissued, because voiding is how an
  obligation is closed without paying it. It creates a new `pending` refund
  with the same kind, items, amount and currency, `reason = 'reissue of <old id>'` and
  `reissue_of_refund_id = old.id` (UNIQUE).
  It sets `reissued_at` on the old one.
- A second reissue gives 409 `reason=already_reissued` with `reissued_by_refund_id`, and a
  replay with the same key returns the stored 201. UNIQUE(`reissue_of_refund_id`) is the
  final guard against two concurrent reissues.
- Balances: a failed refund's items are already reserved (§3.2), so reissue needs no balance
  re-check. It still runs the Q-2 assertion.
- Status: coverage returns (owed → pending counts), so `partially_refunded` → `refunded` where covered.

### 2.5 `POST /api/v1/admin/orders/{order_id}/chargebacks` (required `Idempotency-Key`)
- Request `ChargebackCreate`:
  `{payment_id, provider_dispute_reference: str 1..200, charged_cents > 0, items: [{order_item_id, amount_cents > 0}] (0..50), reason, received_at}`.
- Success is `201 ChargebackDetail`. Errors:
  - 404;
  - 409 `ORDER_NOT_PAID` (an online payment that never reached paid and was not late-captured);
  - 409 `CHARGEBACK_DUPLICATE` (same provider and dispute reference, different body); 409 idempotency;
  - 409 `ORDER_TOTAL_MISMATCH`;
  - 422 `CHARGEBACK_NOT_ONLINE` (a cash payment);
  - 422 `CHARGEBACK_ALLOCATION_INVALID` (items over any line's balance after the voids, or
    `Σ items > charged_cents`);
  - 422 `CHARGEBACK_ITEMS_FORBIDDEN` (items on a late-captured payment).
- `applied_cents = Σ items` and `excess_cents = charged_cents − applied_cents`. Excess raises an
  alert of kind `chargeback_excess`.
- Effects, all in one transaction (§3.3): void all pending and owed refunds on the payment; insert the
  chargeback; move lines; recompute payment and order status; audit; alert.
- `GET /api/v1/admin/orders/{order_id}/chargebacks` lists them.
  `GET /api/v1/admin/chargebacks/{id}` returns the detail.
- **The database enforces the online-only and dedupe rules as well as the service**:
  - `ck_chargebacks_online_only` (`payment_provider <> 'cash'`), backed by the triple FK to
    `payments (id, order_id, provider)`, so the column cannot lie about the payment;
  - `uq_chargebacks_dispute` (`UNIQUE (payment_provider, provider_dispute_reference)`).

  A violation that slips past the service maps to the same 422 or 409. Tests I23 and I24 assert
  each constraint name on a direct INSERT.
- **Production:** production stays on `PAYMENT_PROVIDER=none` until VS-032 (ADR-036 d16,
  `docs/adr/ADR-036-payment-recovery.md:48`; ADR-032 d24). It therefore has no online payment
  to charge back, and the route answers 409 `ORDER_NOT_PAID` or 422 `CHARGEBACK_NOT_ONLINE`
  for every real order. The route ships now, so that VS-032 goes live with refunds and chargebacks
  already tested. It is exercised in dev, CI and staging against `mock` payments only.

### 2.6 `POST /api/v1/admin/cash-blocks/search` (change only)
- It adds one audit row per search: `cash_block.searched`, with `{active, limit, result_count,
  block_ids}`. It **never** records the phone or its hash (Q8; ADR-038 keeps the hash off every
  read surface).
- The audit runs in the route's transaction (`src/app/ordering/api/admin_cash_blocks.py:147-170`).

### 2.7 `POST /api/v1/admin/payments/{payment_id}/record-capture` (decided, Q5)
This resolves VS-024 Q2 (§3.6). It is built in PR C, with a required `Idempotency-Key`.

### 2.8 Jobs
No new cron. The backfill is a one-off, rerunnable data migration (§4.3).
`purge_expired_idempotency_records` already covers the new scopes.

---

## 3. Layers, function by function

### 3.0 Package ownership
- **Payments** owns the four new tables, `app.payments.domain.refunds` (pure rules),
  `app.payments.application.services.refunds` / `.chargebacks` (use cases), the stores
  `app.payments.infrastructure.refunds`, and the routes.
- Payments already imports `app.ordering.public` (`apply.py:12`).
- **Ordering** keeps every `order_items` and `orders.status` write. Its new published functions
  take **refund facts as a parameter**. Ordering never imports Payments, because
  `payments.public` imports `ordering.public` at module load, and the architecture test only
  allows `public`/`ports` crossings (`tests/unit/test_deep_architecture.py`).
- **Fulfillment**'s `OrderPayments` port (`src/app/fulfillment/application/ports.py:47-58`) gains
  `refund_facts(order_id)`, read under the orders lock exactly like `reached_paid`
  (`src/app/fulfillment/infrastructure/delivery_side.py:91-93`).

### 3.1 Pure rules: status derivation (Must-resolve 1 and 6)

**`app.ordering.domain.order_status`** (change, `src/app/ordering/domain/order_status.py:22-55`):

```python
@dataclass(frozen=True)
class RefundFacts:
    """Read under the orders lock; `late_capture` refunds and voided ones never count."""
    covers_paid: bool   # Σ pending+settled refunds + Σ chargeback applied ≥ paid amount
    present: bool       # any pending/settled refund or any chargeback with applied > 0
    owed: bool          # any failed refund not reissued (and not voided)
NO_REFUNDS = RefundFacts(False, False, False)

class OrderStatusInputs:  # `refunds_cover_paid`/`refund_present` replaced by:
    refunds: RefundFacts = NO_REFUNDS

def derive_order_status(i) -> OrderStatus:
    if not i.payment_reached_paid: (unchanged: :38-42)
    if i.refunds.owed:          return PARTIALLY_REFUNDED   # new, first (D1)
    if all_cancelled:           return CANCELLED
    if i.refunds.covers_paid:   return REFUNDED
    if i.refunds.present:       return PARTIALLY_REFUNDED
    if all terminal:            return COMPLETED
    return IN_PROGRESS
```

**Why this order (Must-resolve 1, with evidence):**
- **Case A** (`test_order_status.py:66-70`): a single line fully refunded, then the refund failed.
  The line stays `refunded` (no revert, ADR-024 d11 `:48`).
  - Today: "all lines refunded" fires first → `refunded` while money is owed, which breaks
    ADR-024 d11 ("an owed one keeps the order `partially_refunded`").
  - New: `owed` first → `partially_refunded`. After the reissue, `covers_paid` → `refunded`.
- **Case B** (`:71-75`): every line cancelled, and the cancellation refund failed.
  - Today: `cancelled`. New: `partially_refunded` while owed, then `cancelled` again after the
    reissue (pending counts as non-failed; all-cancelled precedes coverage, as ADR-024 d12 `:49` says).
  - **Where an all-cancelled order with an owed refund lands:** `partially_refunded`. Owed
    money must never read `cancelled`, for the same reason it must never read `completed` (SRS §9.6).
- **"All lines refunded" is dropped.** Proof:
  - A line becomes `refunded` only when its items in non-failed, non-voided refunds *plus*
    failed-not-reissued refunds plus chargeback items reach its total (§3.2 L2).
  - If any of that is failed-not-reissued, `owed` is true and fires first.
  - Otherwise every line is covered by pending, settled or chargeback items, so
    Σ covered = Σ line totals = `orders.total_cents` (Q-2, asserted). That equals the paid amount:
    - online: `decide` requires `captured == payment.amount_cents == order.total_cents`
      (`src/app/payments/domain/outcome.py:50-60`);
    - cash: amount = the live line total at handover (`src/app/ordering/public.py:366`), and
      every line `refunded` means no cancelled line.
  - So `covers_paid` is true and the rule is unreachable. A void (§2.3) never un-refunds a
    line, which is why Q2 limits voids on refunded lines.
  - A property test pins "all lines `refunded` ∧ ¬owed ⇒ covers_paid" against seeded data (§6.2).
- `late_capture` refunds never enter `RefundFacts` (SRS §20.2 `docs/SRS.md:1188`).

**Payment status projection** (new, `app.payments.domain.refunds.payment_status`):
- `covers_paid` → `refunded`; `present or owed` → `partially_refunded`; else `paid`.
- It applies only to a payment in `REACHED_PAID` (`outcome.py:13-15`).
- Recomputed with the order status on create, fail, reissue, void and chargeback, never on settle.
- This adds the back edges `refunded → partially_refunded → paid` that SRS §20.1 lacks
  (ADR-024 appendix `:109`). `ck_payments_cash_shape` (`src/app/payments/infrastructure/models.py:93-97`)
  already allows all three statuses for cash.

**Must-resolve 6: the open-cash count stays status-based.** The plan proves two properties
from the code and pins them with tests:
- **P1. An unpaid, uncancelled cash order always derives `in_progress`.**
  - The unpaid branch returns before any refund input is read (`order_status.py:38-42`).
  - A refund needs a payment that reached paid (§3.2 L0, a FK to `payments`), and a cash
    payment exists only once paid (`ck_payments_cash_shape`; the only writer is
    `insert_cash_payment`, `tests/unit/payments/test_cash_payment_writers.py:15-29`).
  - Chargebacks are online only (CHECK `payment_provider <> 'cash'` plus the composite FK).
  - So no refund fact can exist on an unpaid cash order.
- **P2. A paid cash order never derives `in_progress`.**
  - The handover requires every live line `shipped`/`ready_for_pickup` and moves them all to
    `delivered`/`picked_up` (`src/app/ordering/public.py:374-416`; `handover.py`).
  - No edge leaves `delivered` or `picked_up` (`src/app/ordering/domain/line_transitions.py:33-43`);
    refund and chargeback moves only reach `refunded` or `cancelled`.
  - So every line is terminal after the handover, and the derivation yields one of
    `partially_refunded`, `cancelled`, `refunded` or `completed`.
- Tests: §6.1 U4 (hypothesis over every `OrderStatusInputs` for both methods), plus U5, a
  structural test that fails if any edge out of `delivered` or `picked_up` is ever added. That
  forces VS-031 to revisit `SqlCashChecks.open_order_count` (`src/app/ordering/infrastructure/cash.py:48-57`)
  and `ix_orders_open_cash_phone` (`src/app/ordering/infrastructure/models.py:220-224`).
- Decided (Q12): the count stays status-based. Counting from line states and payments would
  need a new index, and is revisited only if U4 or U5 ever fails.

### 3.1a Old versus new `derive_order_status`: every input compared (Q1)

**Mapping.** The old inputs `(refunds_cover_paid, refund_present)` meant "non-failed refunds
cover paid money" and "any non-failed **or owed** refund" (SRS §20.2, `docs/SRS.md:1188`). For
the comparison, `RefundFacts(c, p, o)` is fed to the new function and `(c, p ∨ o)` to the old one.

**Domain enumerated by the test:**
- `method` ∈ {online, cash} × `cancelled_at_set` ∈ {F, T} × `payment_reached_paid` ∈ {F, T};
- × every multiset of 1 to 3 line states over the 11 `OrderItemStatus` values (363);
- × `(c, p, o)` ∈ {F, T}³.

That is **23,232 cases**.

**Notation** (paid branch only; the unpaid branch, `order_status.py:38-42`, is byte-identical):
- AC = every line `cancelled`;
- AR = every line `refunded`;
- T = every line terminal.
- Old order: AC → `cancelled`; c → `refunded`; AR → `refunded`; p∨o → `partially_refunded`;
  T → `completed`; else `in_progress`.
- New order: o → `partially_refunded`; AC → `cancelled`; c → `refunded`; p → `partially_refunded`;
  T → `completed`; else `in_progress`.

**Every differing output (exhaustive: all other cases are equal):**

| Class | Inputs (paid) | Old | New | Justification |
|---|---|---|---|---|
| D-a | o ∧ AC | `cancelled` | `partially_refunded` | **Intended: PR #8 case B** (`test_order_status.py:71-75`). The cancellation refund failed and money is still owed. ADR-024 d11 says an owed refund keeps the order `partially_refunded`, and the order must not read as closed. After the reissue (o = F) it is `cancelled` again. |
| D-b | o ∧ ¬AC ∧ c | `refunded` | `partially_refunded` | **Unreachable** by invariant I1 (o ⇒ ¬c): an owed refund's amount is reserved (§3.2 L1), so L4 caps Σ pending + settled + chargeback applied at paid − owed < paid. If it were ever reached, the new answer is the safe one: money is still owed. |
| D-c | o ∧ ¬AC ∧ ¬c ∧ AR | `refunded` | `partially_refunded` | **Intended: PR #8 case A** (`test_order_status.py:66-70`). A full refund failed, so the lines stay `refunded` (no revert) but the money is owed. After the reissue (c = T) it is `refunded`. |
| D-d | ¬o ∧ ¬AC ∧ ¬c ∧ AR ∧ p | `refunded` | `partially_refunded` | **Unreachable** by invariant I2 (AR ∧ ¬o ⇒ c; proof in §3.1, using Q-2). This is the dropped "all lines refunded" rule; it only ever fired when c was already true. |
| D-e | ¬o ∧ ¬AC ∧ ¬c ∧ AR ∧ ¬p | `refunded` | `completed` | **Unreachable** by I2, and by invariant I3: a `refunded` line exists only through a refund or a chargeback item, so p ∨ o holds. |

**Invariants** (they hold for every order the code can produce; checked on real rows by U10,
I10 and I25):
- I1: o ⇒ ¬c.
- I2: AR ∧ ¬o ⇒ c.
- I3: any `refunded` line ⇒ p ∨ o.

**Test U15 [M]** (`tests/unit/ordering/test_order_status_old_vs_new.py`):
- It holds `derive_order_status_vs023`, a verbatim copy of `order_status.py:35-55` at `326aa40`,
  frozen in the test module.
- It enumerates the 23,232 cases and collects every case where old ≠ new.
- It asserts the set equals exactly the union of D-a … D-e, with each case classified by its
  predicate. A new difference, or a listed one disappearing, fails with the case printed.
- It asserts every D-b, D-d and D-e case violates `consistent(i) = I1 ∧ I2 ∧ I3`, and that every
  D-a and D-c case satisfies it. So the only reachable changes are the two intended ones.
- It prints the per-class counts for the PR description.

**ADR-042** states that it **amends SRS §20.2** (and database-design §17.2 and the entities
projection). It lists D-a and D-c as the only behaviour changes and cites U15. The SRS and
database-design edits land in PR C with the ADR (§7).

### 3.2 Pure rules: balances (`app.payments.domain.refunds`, new)

Inputs are frozen rows read under the locks:
- `LineFact(id, product_type, status, line_total_cents)`;
- `RefundFact(id, kind, status, reissued, items)`;
- `ChargebackFact(applied_cents, items)`;
- `PaidPayment(id, provider, amount_cents)`.

- **L0 Paid order:** exactly one payment of the order in `REACHED_PAID`. `uq_payments_one_live`
  (`models.py:126-131`) makes it unique. None → `ORDER_NOT_PAID`.
- **L1 Counted items:** items of refunds with status `pending` or `settled`, plus
  `failed` with `reissued = False` (reserved), never `voided`, never `late_capture` (no
  items), plus chargeback items.
- **L2 Line balance** = `line_total − Σ counted items of that line`. The rules on top of that:
  - balance = 0 if the line is `cancelled` and has no counted items: cancelled without a
    refund obligation, which covers a cash refusal (BR-149, ADR-024 d11 `:44`);
  - balance = 0 if the line is `refunded`;
  - an STL line `pending` is unpaid and never in a paid order.
- **L3 Payment balance** = `amount_cents − Σ counted refund amounts on it − Σ chargeback
  applied on it`. Cash: `amount_cents` is the cash recorded (SRS §9.6 "up to the cash recorded").
- **L4 Request check:** each item ≤ its line's balance, and Σ items ≤ the payment balance.
  Otherwise 422 `REFUND_EXCEEDS_AVAILABLE`.
- **L5 Unfinished physical lines** are `pending`, `in_production`, `ready_to_ship`, `shipped` and
  `ready_for_pickup`. A request item that brings such a line's balance to 0 →
  422 `REFUND_REQUIRES_CANCELLATION`, unless the line is in `cancelling` (VS-031's cancellation, §3.7).
- **L6 Lines that become `refunded`:** every requested line whose new balance is 0 and whose
  status is `awaiting_delivery`/`delivered` (STL) or `delivered`/`picked_up`/`returned`
  (physical). The STL leaves the queue (`ix_order_items_stl_awaiting`) and frees ownership
  (`uq_order_items_stl_ownership`, `src/app/ordering/infrastructure/models.py:375-384`). A
  partial refund leaves the line in its state.
- **L7 Q-2:** `orders.total_cents == Σ line_total_cents`. For online,
  `payment.amount_cents == orders.total_cents` too. Otherwise `OrderTotalMismatch`: nothing
  written, an `error` log `refund_integrity_error`, and a `payment` alert.
- **L8 RefundFacts** (§3.1) from the same rows.

All of these are pure functions with no I/O. They are unit-tested exhaustively and with
hypothesis (§6.1). Concurrency safety comes from the lock (§8.1), not from these functions.

### 3.3 Use cases (`app.payments.application.services.refunds` / `.chargebacks`, new)

```python
async def create_refund(orders: OrderSide, refunds: RefundStore, payments: PaymentStore,
    audit, notices, *, order_id, kind: RefundKind, lines: Sequence[RefundLine], reason,
    requested_by: UUID | None, cancelling: frozenset[UUID] = frozenset(),
    at) -> RefundRecord
```
1. `locked = orders.lock(order_id)`, which is `lock_order_for_change`: `orders`, then **every**
   line by id (`src/app/ordering/public.py:152-158`). None → `OrderNotFound`. A line of the
   request that is not in `locked.lines` → `LineNotFound` (404).
2. L7 (Q-2).
3. `paid = payments.lock_paid_for_order(order_id)` (new). This is `lock_for_order`
   (`src/app/payments/infrastructure/payments.py:182-186`: all attempts by id `FOR UPDATE`),
   then the one in `REACHED_PAID`. None → `OrderNotPaid`.
4. `facts = refunds.order_facts(order_id)`, unlocked reads made after the locks (READ
   COMMITTED: each new statement sees every commit made before this transaction got the
   orders lock).
5. L2–L5, then L6.
6. `refunds.insert(...)` plus items. Then `orders.refund_lines(locked, ids, actor, at)`
   (new Ordering writer, §3.4). Then `payments.set_status(paid.id, payment_status(...))` if changed.
7. `orders.recompute(locked, refunds=facts')`.
8. Audit `refund.created`. Notices: the `refund_issued` email and a `refund` notification for
   `admin` and `cancellation` (Q7).

`settle_refund`, `fail_refund`, `void_refund` and `reissue_refund` follow the same shape:
learn `order_id` unlocked, steps 1–4, then `refunds.lock(refund_id)` (rank 4), then the
decision on the locked row, the writes, the recompute (not on settle), audit and notices.

```python
async def record_chargeback(..., *, order_id, payment_id, dispute_ref, charged_cents,
    lines, reason, received_at, recorded_by, at) -> ChargebackRecord
```
1. Lock steps 1–3. Here the payment is `payment_id`, re-checked to belong to the order and to
   be online; it must be in `REACHED_PAID` **or** have `late_captured_at`.
2. Lock every pending and owed refund on that payment by id (rank 4). Void them all:
   `voided_by = recorded_by` and `void_reason = "absorbed by chargeback <id>"`.
   - **Payout invariant:** after this, money still to leave the business on this payment = 0,
     so settled + chargeback applied ≤ paid. Anything the bank took beyond that is
     `excess_cents` (Must-resolve 2).
3. **A normal (paid) payment:** validate the items against L2/L3 recomputed after the voids
   (`applied ≤ payment balance`, each item ≤ its line's balance, `applied ≤ charged`). Then:
   - insert the chargeback and its items;
   - set each line whose balance is now 0:
     - terminal (`delivered`, `picked_up`, `returned`) or STL (`awaiting_delivery`,
       `delivered`) → `refunded`;
     - **unfinished physical (L5 set) → `cancelled`**, with `cancelled_at`, `cancel_reason` NULL
       and history reason `chargeback` (Must-resolve 4; ADR-024 d16's wording fixed, §7).
     - A partially covered unfinished line keeps moving.
   - Then recompute both statuses.
   - Must-resolve 4's second hole, "a fully charged-back `shipped` or `returned` line has no
     exit", is closed: `shipped` is cancelled here and `returned` becomes `refunded` here.
     VS-031 therefore needs no `returned → refunded` override.
4. **A late-captured payment:** no items allowed. Let `L` be the voided live `late_capture`
   refund (amount `a`, if any).
   - `applied_cents = min(charged, a)` and `excess = charged − applied`.
   - If `charged < a`: insert a new pending `late_capture` refund for `a − charged` with
     `reissue_of_refund_id` NULL and reason "remainder after chargeback <id>". The unique live
     index allows it because `L` is now voided.
   - Statuses: none change (late captures never count).
   - This defines "a chargeback on a late-captured attempt" (Must-resolve 2, last sentence).
5. Audit `chargeback.recorded` (with the voided refund ids). Alert `chargeback_excess` when
   `excess > 0`, plus an `info` alert per chargeback.

### 3.4 Ordering changes (`src/app/ordering/public.py`, `infrastructure/orders.py`)

- `status_inputs_for(locked, lines, *, reached_paid, refunds: RefundFacts)` replaces the
  stop-gap (`public.py:230-241`). The `refund_present=… is PARTIALLY_REFUNDED` line is
  deleted, and the docstring loses "STOP-GAP".
- Callers updated, each receiving facts from its caller:
  - `mark_stl_line_delivered` (`:292`): `DeliveryOrders.mark_delivered` gains `refunds`, read in
    `deliver_stl_line` via the `OrderPayments` port;
  - `transition_physical_line` (`:352`): `transition_line.py:61` reads `refund_facts` next to `reached_paid`;
  - `hand_over_cash_lines` (`:414`): it passes `NO_REFUNDS`, because a cash order has no
    payment, and so no refund, before this INSERT. A unit test asserts that.
- `mark_order_paid` (`:189-227`) and `release_unpaid_order` (`:454-503`) keep the defaults: no
  refund can exist before the first payment reaches paid, or on an unpaid order.
- New: `refund_lines(session, locked, line_ids, *, actor_user_id, reason, at)` sets each to
  `refunded` through `set_line_status`, adds history rows, and **does not recompute** (the
  caller does, with fresh facts).
- New: `cancel_lines_for_chargeback(session, locked, line_ids, *, actor_user_id, at)` (`cancelled`,
  `cancelled_at`).
- Both are added to `KNOWN_LINE_STATUS_CALLERS` in `tests/unit/ordering/test_order_item_writers.py:20-23`,
  with the reason "only under the orders lock".
- `recompute_order_status` (`:161-186`) is unchanged; it stays the only `orders.status` writer.
- **The strict-xfail test, deliberately:** `tests/unit/ordering/test_status_inputs.py:79-81`
  (`test_a_refunded_order_stays_refunded_after_a_physical_transition`).
  - With the new signature it is rewritten to pass `RefundFacts(covers_paid=True, …)`, and the
    `xfail(strict=True)` marker is removed in the same commit.
  - The commit message names ADR-039 d7 and ADR-040 (`docs/adr/ADR-040-…md:34`).
  - `:53-55` and `:73-76` are rewritten to real facts: a `partially_refunded` order stays so
    because `present=True`, not because of its old status.
  - `tests/integration/fulfillment/test_stl_delivery_api.py:287-296` currently seeds `orders.status`
    directly. It is rewritten to seed a real `refunds` row plus items, and asserts
    `partially_refunded` after the delivery.
  - `test_order_status.py:64-75` (the PR #8 cases) flip to `PARTIALLY_REFUNDED`, with the ADR-042 reference.

### 3.5 Late capture through the existing hook (D10)

- **Binding:** `SqlLateCaptureRefunds(alerts, refunds)` in `app.payments.infrastructure.alerts`
  replaces `SqlLateCaptureAlerts` at `src/app/payments/infrastructure/verification.py:59`, the
  only binding (grep: `late_captures=` appears once). It is still called from
  `_late_capture` (`apply.py:199-207`) after `mark_late_capture` (`payments.py:151-170`), in
  Tx B, with orders, lines and payment already locked. The `refunds` INSERT is therefore the
  last lock (rank 4).
- `late_capture_recorded(locked, payment, captured_amount_cents, captured_currency, reason, at)`:
  1. raise the existing alert (unchanged body, `alerts.py:138-161`);
  2. `amount = captured_amount_cents`, or `payment.amount_cents` when the provider
     reported none, with reason "provider reported no amount; check the dashboard" (Q6);
  3. skip when `amount = 0`, with a log only;
  4. `currency = captured_currency or payment.currency`. A non-USD currency is stored exactly
     as reported, **never converted** (Q6). The admin refunds it in that currency in the dashboard.
     Analytics (VS-043) never count `late_capture` refunds, so no conversion is ever needed;
  5. `INSERT … ON CONFLICT DO NOTHING` on `uq_refunds_one_live_late_capture`, with `kind = late_capture`,
     `requested_by` NULL, no items and `status = pending`.
- **Cap:** `amount ≤ captured_amount_cents` by construction. It is never capped by
  `amount_cents`, because an overpayment exceeds it (ADR-024 appendix `:99`; VS-024 plan `:869`).
  No order or payment status recompute: late captures never count, and the payment stays
  `failed`/`expired` (`ck_payments_late_capture`, `models.py:98-101`).
- **One per payment:**
  - `mark_late_capture` already only fires once (`WHERE late_captured_at IS NULL`, `payments.py:168-170`);
  - `decide` gets `already_late_captured` (`apply.py:62`);
  - the partial unique index is the final guard.

  So two distinct provider events create one refund.
- **Manual confirm:** it goes through `apply_provider_result` (`manual.py` imports it), so it
  gets the same binding.
- **Backfill:** see §4.3.

### 3.6 VS-024 owner question Q2: a capture with no matching payment record

- The evidence: manual confirm with a differing amount is a 422 that writes nothing (ADR-036 d7,
  `docs/adr/ADR-036-…md:27`), and the platform then has no row (VS-024 plan `:438-442`, case
  R-f `:536`).
- **Decided (Q5):** PR C adds
  `POST /api/v1/admin/payments/{payment_id}/record-capture` (admin, MFA, CSRF and a required
  `Idempotency-Key`), with the body `{captured_amount_cents > 0, captured_currency, dashboard_reference, reason}`.
- It is allowed only for an online attempt that is not in `REACHED_PAID` and has no
  `late_captured_at`, on a provider with **no status API** (`capability(...)` is
  `NO_STATUS_QUERY`, `verification.py:63-68`). A provider with a status API reports the real
  capture through reconciliation.
- It runs the normal late-capture path through `apply_result`, with a synthetic
  `ProviderResult("paid", amount, currency)` and `source="manual"`, so the lock order, the
  alert and the refund come for free.
  - With a matching amount, `decide` would return `APPLY_PAID`. The route therefore **refuses
    a matching amount** (409 `reason=use_confirm`), so only a mismatch can be recorded.
- ADR-036's typo concern (`:67`) is answered by:
  - the obligation is manual, and the admin checks the dashboard before paying;
  - the `void` route (§2.3) closes a mistaken one;
  - the audit row records the typed values.
- Alternative: keep R-f outside the platform (the release reason only). That is cheaper, but
  the money is then invisible to the queue and to BR-126.

### 3.7 Published interface (what VS-031, VS-032, VS-036, VS-043 and VS-045 consume)

From `app.payments.public` (all on the caller's session and transaction; the caller has
taken **no** lock yet unless stated):

```python
RefundKind = Literal["admin", "cancellation", "late_capture"]
@dataclass(frozen=True) class RefundLine: order_item_id: UUID; amount_cents: int
@dataclass(frozen=True) class LineBalance: order_item_id: UUID; balance_cents: int
@dataclass(frozen=True) class RefundRecord: id: UUID; kind: RefundKind; status: str; amount_cents: int; items: tuple[RefundLine, ...]

async def refund_balances(session, locked: LockedOrder) -> tuple[tuple[LineBalance, ...], int]
    """Per-line and payment balances. Caller holds orders + lines (lock_order_for_change)."""
async def create_refund(session, locked: LockedOrder, *, kind: RefundKind, lines, reason,
    requested_by: UUID, cancelling: frozenset[UUID] = frozenset(), at) -> RefundRecord
    """Caller holds orders + lines; this locks the payment, inserts, moves covered lines to
    refunded (not those in `cancelling`) and does NOT recompute: the caller does, last."""
async def refund_facts(session, order_id: UUID) -> RefundFacts   # read under the orders lock
async def record_chargeback(session, *, order_id, payment_id, ...) -> ChargebackRecord  # VS-032
async def refunded_cents_by_line(session, line_ids) -> dict[UUID, int]   # VS-043; counts pending+settled+chargeback applied, never failed/voided/late
async def unsettled_refund_exists(session, user_id: UUID) -> bool        # VS-045; pending, owed, live late_capture
```

- **VS-031 cancel** follows the ADR-024 d9 row (`docs/adr/ADR-024-…md:31`):
  1. `lock_order_for_change`;
  2. `refund_balances`;
  3. `create_refund(kind="cancellation", lines=[(id, balance) for balance > 0], cancelling={ids})`,
     which locks the payment and inserts the refund;
  4. Ordering's cancel writer (VS-031) moves the lines to `cancelled`;
  5. (cash refusal only) cart → phone lock → block;
  6. `recompute_order_status(..., status_inputs_for(..., refunds=await refund_facts(...)))`.

  An unpaid cash line produces no `create_refund` call (`ORDER_NOT_PAID` is never reached,
  because VS-031 checks cash and unpaid first).
- **VS-036:** hook point after `create_refund`, `void_refund`, `fail_refund`, `reissue_refund`
  and `record_chargeback`. It is a no-op in VS-030.
- **VS-032:** `record_chargeback` is provider-neutral. A dispute webhook (if any) calls it with
  `provider_dispute_reference` as its dedupe key.

---

## 4. Database

### 4.1 Is a migration needed?
Yes: four tables, two enums and the Q-1 constraint (PR A), plus one data migration (PR C).
Every change is additive: old code ignores the new tables, and the only writer of
`order_items` already copies `order.user_id` (`src/app/ordering/infrastructure/orders.py:106`,
cited by the audit at `docs/audits/VS-041-audit.md:257`), so the FK accepts it.

### 4.2 Migration `<rev>_refunds_and_chargebacks.py` (`down_revision = "0f43e238eaae"`)

The steps run in order:

1. `CREATE TYPE refund_kind AS ENUM ('admin','cancellation','late_capture')`, and
   `CREATE TYPE refund_status AS ENUM ('pending','settled','failed','voided')`.
2. **Q-1, the precheck:** `SELECT count(*) FROM order_items i JOIN orders o ON o.id = i.order_id WHERE
   i.user_id <> o.user_id`. If it is > 0, raise with the count (never auto-fix customer data).
3. Add the supporting keys:
   - `ALTER TABLE orders ADD CONSTRAINT uq_orders_id_user UNIQUE (id, user_id)`;
   - `ALTER TABLE order_items ADD CONSTRAINT uq_order_items_id_order UNIQUE (id, order_id)`;
   - `ALTER TABLE payments ADD CONSTRAINT uq_payments_id_order_provider UNIQUE (id, order_id, provider)`.
4. Add `ALTER TABLE order_items ADD CONSTRAINT fk_order_items_order_owner FOREIGN KEY (order_id, user_id)
   REFERENCES orders (id, user_id) ON DELETE RESTRICT ON UPDATE RESTRICT NOT VALID`, then
   `VALIDATE CONSTRAINT fk_order_items_order_owner`. This mirrors `fk_order_items_offer_owner`
   (`migrations/versions/4b7e2c9d1f30_offers_and_offer_rounds.py:164-172`).
5. Create `refunds`:
   - Columns:
     - `id uuid PK default gen_random_uuid()`, `order_id uuid NOT NULL`, `payment_id uuid NOT NULL`,
       `payment_provider payment_provider NOT NULL`;
     - `kind refund_kind NOT NULL`, `status refund_status NOT NULL DEFAULT 'pending'`;
     - `amount_cents bigint NOT NULL`, `currency char(3) NOT NULL DEFAULT 'USD'`, `reason text NOT NULL`;
     - `requested_by uuid NULL FK users RESTRICT`, `approved_by uuid NULL FK users RESTRICT`;
     - `reissue_of_refund_id uuid NULL FK refunds RESTRICT`, `reissued_at timestamptz`;
     - `settled_at timestamptz`, `settled_by uuid FK users`, `settlement_reference text`, `settlement_note text`;
     - `failed_at`, `failed_by`, `failure_reason`, `voided_at`, `voided_by`, `void_reason`;
     - `initiated_at timestamptz NOT NULL`, `created_at`/`updated_at timestamptz NOT NULL DEFAULT now()`.
   - Constraints:
     - FK `(payment_id, order_id, payment_provider) → payments (id, order_id, provider)` RESTRICT
       (the payment belongs to the order);
     - FK `order_id → orders` RESTRICT;
     - `uq_refunds_id_order UNIQUE (id, order_id)`;
     - `uq_refunds_reissue_of UNIQUE (reissue_of_refund_id)`.
   - CHECKs:
     - `ck_refunds_amount`: `amount_cents > 0`;
     - `ck_refunds_currency`: `currency = 'USD' OR (kind = 'late_capture' AND currency ~ '^[A-Z]{3}$')`;
     - `ck_refunds_requester`: `requested_by IS NOT NULL OR kind = 'late_capture'`;
     - `ck_refunds_reissued_failed`: `reissued_at IS NULL OR status = 'failed'`;
     - `ck_refunds_late_capture_online`: `kind <> 'late_capture' OR payment_provider <> 'cash'`;
     - `ck_refunds_state_stamps`: `(status = 'settled') = (settled_at IS NOT NULL)`, the same for
       `failed`/`failed_at`, and for `voided`/`voided_at`; `voided` also requires `void_reason IS NOT NULL`;
     - `ck_refunds_text_lengths`: `char_length(reason) BETWEEN 1 AND 1000`, settlement reference ≤ 200,
       notes ≤ 1000;
     - `ck_refunds_void_never_settled`: `NOT (status = 'voided' AND settled_at IS NOT NULL)`, so a
       settled refund can never become voided even through a bad UPDATE;
     - `ck_refunds_void_not_reissued`: `NOT (status = 'voided' AND reissued_at IS NOT NULL)`.
     - "A voided refund is never reissued" is cross-row (the new row's `reissue_of_refund_id`).
       The reissue service enforces it under the refund's `FOR UPDATE`, with races R13 and R14.
   - Indexes:
     - `uq_refunds_one_live_late_capture` on `(payment_id) WHERE kind = 'late_capture' AND
       status NOT IN ('failed','voided')`;
     - `ix_refunds_obligations` on `(created_at, id) WHERE status = 'pending' OR (status = 'failed' AND
       reissued_at IS NULL)` (`docs/requirments/database-design.md:2286-2291`);
     - `ix_refunds_order` on `(order_id, created_at)`;
     - `ix_refunds_payment` on `(payment_id)`.
6. Create `refund_items`:
   - Columns: `id`, `refund_id`, `order_id`, `order_item_id`, `amount_cents bigint CHECK > 0`, `created_at`.
   - FKs: `(refund_id, order_id) → refunds (id, order_id)` and `(order_item_id, order_id) →
     order_items (id, order_id)`, both RESTRICT, so an item can never name another order's line.
   - `UNIQUE (refund_id, order_item_id)`; `ix_refund_items_line (order_item_id)`.
7. Create `chargebacks`:
   - Columns: `id`, `order_id`, `payment_id`, `payment_provider`, `provider_dispute_reference text
     NOT NULL (1..200)`, `charged_cents bigint`, `applied_cents bigint`, `excess_cents bigint`,
     `currency char(3) = 'USD'`, `reason text (1..1000)`, `recorded_by uuid NOT NULL FK users`,
     `received_at`, `created_at`.
   - CHECKs:
     - `ck_chargebacks_money`: `charged_cents > 0 AND applied_cents >= 0 AND excess_cents >= 0 AND
       applied_cents + excess_cents = charged_cents`;
     - **`ck_chargebacks_online_only`**: `payment_provider <> 'cash'`;
     - `ck_chargebacks_dispute_reference`: `char_length(provider_dispute_reference) BETWEEN 1 AND 200`.
   - The same triple FK to payments (`fk_chargebacks_payment`), so `payment_provider` is the
     payment's real provider.
   - **`uq_chargebacks_dispute`** `UNIQUE (payment_provider, provider_dispute_reference)`;
     `uq_chargebacks_id_order`; `ix_chargebacks_order (order_id, created_at)`.
8. Create `chargeback_items`, shaped like `refund_items`, with FKs to `chargebacks (id, order_id)` and
   `order_items (id, order_id)`.
9. There is no change to `payment_status`: its existing values already cover the projection.

`downgrade()`: drop in reverse (the items tables, `chargebacks`, `refunds`, the FK, the three
uniques, the two types). This is safe while the tables are empty or disposable. In production, a
downgrade after real refunds exist is a restore, not a downgrade (database-design §26 rule 5).
The data steps need no `CONCURRENTLY`: `orders`, `order_items` and `payments` are small in V1.
The precheck guards `VALIDATE`.

### 4.2a PR A order of operations, locks, and merge rule

PR A runs as **one Alembic transaction** (the default). `SET LOCAL lock_timeout = '5s'` comes
first, so a step that would queue behind live traffic fails cleanly instead of stalling checkout.
Every lock below is held until COMMIT. The three tables are small in V1, so the whole
migration takes well under a second. Deploy it at low traffic anyway.

| # | Step | Lock taken (PostgreSQL) | Notes |
|---|---|---|---|
| 0 | `SET LOCAL lock_timeout = '5s'` | none | The migration fails, and nothing is applied, if a lock is not granted in 5 s. |
| 1 | `CREATE TYPE refund_kind`, `refund_status` | catalog only | No table lock. |
| 2 | **Precheck:** `SELECT i.id, i.order_id FROM order_items i JOIN orders o ON o.id = i.order_id WHERE i.user_id <> o.user_id LIMIT 20`, plus `count(*)` | `ACCESS SHARE` on both | If the count is > 0: `raise RuntimeError("fk_order_items_order_owner: N mismatched lines, e.g. …")`, naming line and order ids only (no user ids or emails). The transaction rolls back and nothing is applied. **Customer data is never auto-fixed.** |
| 3 | `ALTER TABLE orders ADD CONSTRAINT uq_orders_id_user UNIQUE (id, user_id)` | `ACCESS EXCLUSIVE` on `orders` (builds the index) | It blocks reads and writes on `orders` for the index build. This is acceptable at V1 size; otherwise `CREATE UNIQUE INDEX CONCURRENTLY` plus `ADD CONSTRAINT … USING INDEX` in an `autocommit_block`. |
| 4 | `ALTER TABLE order_items ADD CONSTRAINT uq_order_items_id_order UNIQUE (id, order_id)` | `ACCESS EXCLUSIVE` on `order_items` | As 3. |
| 5 | `ALTER TABLE payments ADD CONSTRAINT uq_payments_id_order_provider UNIQUE (id, order_id, provider)` | `ACCESS EXCLUSIVE` on `payments` | As 3. |
| 6 | `ALTER TABLE order_items ADD CONSTRAINT fk_order_items_order_owner FOREIGN KEY (order_id, user_id) REFERENCES orders (id, user_id) ON DELETE RESTRICT ON UPDATE RESTRICT NOT VALID` | `SHARE ROW EXCLUSIVE` on `order_items` and on `orders` | **No scan** of existing rows. New and updated rows are checked from this moment, so no mismatch can appear between step 2 and step 7. |
| 7 | `ALTER TABLE order_items VALIDATE CONSTRAINT fk_order_items_order_owner` | `SHARE UPDATE EXCLUSIVE` on `order_items`, `ROW SHARE` on `orders` | Scans the existing rows. It allows concurrent reads and writes (but the lock is still held until COMMIT, because of the single transaction). The step-2 precheck makes failure here practically impossible. If it fails anyway, the whole migration rolls back. |
| 8 | `CREATE TABLE refunds`, `refund_items`, `chargebacks`, `chargeback_items` with their CHECKs, FKs and indexes (§4.2 steps 5–8) | `SHARE ROW EXCLUSIVE` on `orders`, `order_items`, `payments` and `users` (FK targets) | The new tables are empty. |

- **Why `NOT VALID` then `VALIDATE` inside one transaction:** it keeps the same two-phase shape
  as `fk_order_items_offer_owner` (`migrations/versions/4b7e2c9d1f30_offers_and_offer_rounds.py:164-172`).
  The validation becomes a separate, cheaper step if V2 ever needs to split it across
  transactions. At V1 size the single transaction keeps the migration atomic and rerunnable:
  a failed run leaves nothing behind, and Alembic does not stamp it.
- `downgrade()` reverses 8 → 3 (drop the tables, the FK, the three uniques, the two types)
  under the same `lock_timeout`.
- **Test** (I6, plus the schema tests):
  - upgrade on seeded matched data → the constraints exist and `convalidated` is true;
  - upgrade on a database seeded with one mismatched line → `RuntimeError` naming
    `fk_order_items_order_owner`, with no new constraint or table and the version unchanged;
  - downgrade then upgrade round-trips.
- **Merge rule:** **PR A merges alone, before any code uses it.** It ships the ORM models
  but no route, service or store reads or writes the new tables. `main` then runs on the new
  schema with unchanged behaviour (the new FK only constrains what the existing writer already
  guarantees, `orders.py:106`). PR B branches from `main` only after PR A is merged and
  migrated on staging.

### 4.3 PR C data migration `<rev>_backfill_late_capture_refunds.py` (revises PR A's)

It runs in Python inside the migration (`op.get_bind()`), not as one SQL statement, so a
malformed audit row is skipped and reported instead of aborting the cast for every row.

- **Marker:** every row it creates has `reason = 'late capture (backfill <rev>)'`, where `<rev>` is
  the revision id. No other writer uses that text:
  - the live sink writes its own reason (§3.5);
  - the admin create route always records `kind = admin`;
  - reissue writes `reason = 'reissue of <id>'`.

  The marker identifies exactly the rows this migration created.
- **Batches** of 500 payments, keyset on `payments.id`:
  `SELECT id, order_id, provider, amount_cents, currency, captured_amount_cents,
  captured_currency, late_captured_at FROM payments WHERE late_captured_at IS NOT NULL AND id > :after
  ORDER BY id LIMIT 500`. This is served by `ix_payments_late_captured` (`models.py:145-149`) plus
  the PK. Each batch is its own `INSERT … ON CONFLICT DO NOTHING`.
- **The amount and currency for each payment, in order:**
  1. `payments.captured_amount_cents` / `captured_currency` (VS-024 rows);
  2. else the oldest `audit_logs` row with `entity_type = 'payment' AND entity_id = p.id AND
     action = 'payment.late_capture'` (written by `apply.py:179-195`; VS-024 plan `:863-866`).
     It is parsed in Python: `captured_amount_cents` must be an `int` (or an integer string)
     `> 0`, and `captured_currency`, if present, must match `^[A-Z]{3}$`;
  3. else, **when no such audit row exists**, the attempt's `amount_cents` / `currency`,
     flagged in the reason (Q6: never lose an obligation).
- A non-USD currency is stored as reported, never converted (Q6).
- **Skipped and reported, never guessed:** an audit row that exists but is malformed, meaning
  any of the following, causes the payment to be **skipped**:
  - `after_data` is not an object;
  - the amount is missing, non-numeric, a float, ≤ 0 or larger than 10^12;
  - the currency is malformed.

  Also skipped are payments whose resolved amount is 0. Each skip is logged as
  `late_capture_backfill_skipped` with the payment id and the reason code (`audit_malformed`,
  `amount_zero`), and never the payload. The migration ends with one summary line:
  `late_capture_backfill: scanned=N created=N existing=N skipped=N`. The skipped payment ids
  are also written to an audit row `refund.backfill_skipped` (actor NULL), so they are visible
  in the admin audit viewer and can be handled by hand (the record-capture route, §2.7).
- **Idempotent:**
  - `ON CONFLICT DO NOTHING` on `uq_refunds_one_live_late_capture` means a payment that already
    has a live late-capture refund (from the live sink, or a previous run) gets nothing;
  - a rerun creates no duplicates and reports them as `existing`;
  - a concurrent live late capture racing the backfill is resolved by the same index.
- **`downgrade()` deletes only rows it created, and only those nothing depends on:**
  `DELETE FROM refunds r WHERE r.kind = 'late_capture' AND r.reason LIKE 'late capture (backfill <rev>)%'
  AND r.status = 'pending' AND NOT EXISTS (SELECT 1 FROM refunds x WHERE x.reissue_of_refund_id = r.id)`.
  - Backfilled rows the admin has since settled, failed or voided are **kept**, because they
    are money history. They are counted in a `late_capture_backfill_downgrade_kept=N` log line.
  - Rows from the live sink or record-capture never match the marker.
- **Test I16 [M]** (`tests/integration/payments/test_late_capture_backfill.py`, running the
  migration functions against real Postgres). It seeds payments with `late_captured_at` set as follows:
  - (a) with `captured_amount_cents`;
  - (b) without it, but with a well-formed audit row;
  - (c) without it, and an audit row whose amount is `"abc"`;
  - (d) the same, with the amount `-5`;
  - (e) the same, with `after_data` a JSON string;
  - (f) without it, and no audit row;
  - (g) with a live late-capture refund already present;
  - (h) a non-USD capture (`LBP`).

  It asserts:
  - created = {a, b, f, h} with the right amounts and currencies (h stays `LBP`), and f flagged;
  - skipped = {c, d, e}, each with its reason code and the summary line;
  - g untouched;
  - a second run creates nothing;
  - a 1,200-payment seed runs in 3 batches;
  - downgrade deletes only the pending backfilled rows: a backfilled row first settled, and g's
    live row, survive.

### 4.4 Rows VS-030 writes in existing tables
- `order_items`: `fulfillment_status` → `refunded`/`cancelled`, plus `cancelled_at`.
- `order_status_history`, `orders.status`.
- `payments.status`, plus `updated_at`.
- `audit_logs`, `email_outbox`, `notifications`, and `idempotency_records` (scopes
  `admin_refund_create`, `admin_refund_reissue`, `admin_chargeback_create`, `admin_record_capture`).

---

## 5. Performance and abuse

- **Per-order work** is tiny and bounded:
  - a refund names ≤ 50 lines;
  - balance reads are `refund_items` by `order_id` (`ix_refunds_order` plus the composite FK
    index), at most a few dozen rows;
  - the lock scope is one order.
- **The obligations queue** is a partial index scan (`ix_refunds_obligations`), and the cursor
  is keyset `(created_at, id)`. The queue cannot grow without bound in practice: each row is
  an action the admin takes.
- **Lock hold time:** the transaction makes no provider call (D12). Outbox emails are rows only
  (`delivery_side.py:117-135` pattern).
- **Abuse:**
  - admin-only, MFA, CSRF, and per-admin rate limits (write 60/h, read 300/h);
  - `Idempotency-Key` on every creating route;
  - hostile bodies: `extra="forbid"`, max lengths, `amount_cents` positive and `≤ 10^9`;
  - the boundary test matrix walks the new prefixes (§6.5).
- **Money invariants enforced in the database:**
  - positive amounts;
  - the triple FK (a refund's payment is the order's; a chargeback's is online);
  - the composite item FKs (an item's line is the refund's order);
  - one live late capture per payment;
  - one reissue per failed refund;
  - a unique dispute reference.

  The cross-row sums (L2–L4) are enforced under the `orders` lock, as database-design §9.4
  (`:1444`) requires.
- **Logs:** `refund_created`, `refund_integrity_error` (error) and `chargeback_excess` (error),
  with ids only. Never a phone, hash, email, address or dashboard reference beyond the admin's
  own `settlement_reference`, which is stored but never logged.

---

## 6. Tests (per category; `tests/<category>/…`)

[M] = must-have; [N] = nice-to-have. Every money, race, lock-order, balance and
status-derivation test is [M]. Concurrency tests use the existing `meet_or_fail` barrier
pattern and real Postgres.

### 6.1 Unit (`tests/unit/payments/test_refund_rules.py`, `tests/unit/ordering/…`)
- U1 [M] `derive_order_status` table, the new order:
  - case A → `partially_refunded`, and after the reissue `refunded`;
  - case B → `partially_refunded`, and after the reissue `cancelled`;
  - covered → `refunded`; present → `partially_refunded`; owed beats every later rule.
  - It replaces `test_order_status.py:64-75`.
- U2 [M] Hypothesis: `owed ⇒ PARTIALLY_REFUNDED` whenever paid, and `status ∈ OrderStatus`.
  The existing `pending_payment` property (`:84-106`) is kept, with `RefundFacts` drawn.
- U3 [M] The payment-status projection: every combination of `covers_paid`, `present` and
  `owed` → `paid`, `partially_refunded` or `refunded`, including the back edges.
- U4 [M] **Must-resolve 6:**
  - P1: for CASH ∧ ¬paid ∧ ¬all-cancelled → `IN_PROGRESS` over every `RefundFacts` and every line mix;
  - P2: for CASH ∧ paid ∧ all lines in {delivered, picked_up, refunded, cancelled} → never `IN_PROGRESS`;
  - both by hypothesis.
- U5 [M] Structural: no edge in `DELIVERY_EDGES`/`PICKUP_EDGES` leaves `delivered` or
  `picked_up` (`line_transitions.py:33-43`). The failure message names `open_order_count`.
- U6 [M] Balances L1–L3: failed-not-reissued is reserved; reissued failed and voided are not
  counted; late_capture never counts; a cancelled line without items is 0; a `refunded` line is 0;
  chargeback items count.
- U7 [M] L4/L5:
  - exactly the balance on a delivered physical line succeeds; one cent over is 422;
  - emptying each of the five unfinished states is 422 `REFUND_REQUIRES_CANCELLATION`, and
    partial succeeds;
  - `cancelling` exempts a line.
- U8 [M] L6: which lines become `refunded` per state; a partial leaves the state; an STL
  `awaiting_delivery` covered becomes `refunded`.
- U9 [M] Q-2 L7: total ≠ Σ lines, and online `amount_cents ≠ total` → `OrderTotalMismatch`.
- U10 [M] Hypothesis over random request sequences against one ledger: Σ counted ≤ paid
  always, each line's coverage ≤ its total, and "all lines refunded ∧ ¬owed ⇒ covers_paid".
- U11 [M] `test_status_inputs.py` rewritten (§3.4). The strict-xfail becomes a plain passing
  test; `hand_over_cash_lines` passes `NO_REFUNDS`.
- U12 [M] Writer allow-lists:
  - `KNOWN_LINE_STATUS_CALLERS` gains `refund_lines` and `cancel_lines_for_chargeback`;
  - `test_every_payments_insert_is_known` is unchanged, because refunds are not payments;
  - a new `test_refund_writers.py` lists every INSERT/UPDATE of `refunds`, `refund_items`,
    `chargebacks` and `chargeback_items`, and the callers of each, so a writer that skips
    the orders lock fails.
- U13 [M] Chargeback allocation: void-all-then-allocate; `applied + excess = charged`; a
  late-captured payment with no items; `charged < a` leaves a remainder refund.
- U14 [N] Request hashing: item order does not change the hash.
- U15 [M] Old versus new `derive_order_status` over all 23,232 input combinations; the diff set
  equals exactly D-a … D-e, and D-b, D-d and D-e are all inconsistent (§3.1a).
- U16 [M] The refund state machine as a table: `pending → settled | failed | voided`,
  `failed → voided` (only when not reissued), `failed → (reissued)`. `settled` and `voided`
  are terminal. Every other pair is refused with its stable `reason`.

### 6.2 Integration (real Postgres; `tests/integration/payments/test_refunds_api.py`, `…/test_chargebacks_api.py`, `…/ordering`)
- I1 [M] Create on a paid online STL+physical order: 201, rows, items, audit, outbox, notification,
  payment `partially_refunded`, order `partially_refunded`.
- I2 [M] Partial then rest, on a delivered physical line and on an STL `awaiting_delivery` line:
  - the first keeps the state, the queue entry and ownership;
  - the second makes the line `refunded`, out of the queue and not owned;
  - the order goes `partially_refunded` → `refunded`.
- I3 [M] An unpaid online order and an unpaid cash order → 409 `ORDER_NOT_PAID`, nothing written.
- I4 [M] Cash after handover: capped at the cash recorded (one cent over is 422). A cancelled
  line of a paid cash order is 422.
- I5 [M] Q-2: a seeded `total_cents` mismatch → 409 `ORDER_TOTAL_MISMATCH`, zero rows, an error log.
- I6 [M] Q-1: an INSERT of an `order_items` row whose `user_id` differs from the order's →
  `IntegrityError fk_order_items_order_owner`. The migration precheck refuses mismatched seed data.
- I7 [M] Idempotency:
  - a replay returns the same 201 plus `Idempotent-Replayed`, and no second row;
  - the same key with a different body → 409 conflict;
  - a 422 stores nothing, and the same key then succeeds.
- I8 [M] Settle:
  - the order and payment statuses are unchanged; settle twice → 200 same;
  - settling a failed or voided refund → 409.
- I9 [M] Fail:
  - the line stays `refunded`, the refund appears in the queue as owed, and the order goes
    `refunded` → `partially_refunded`;
  - the amount cannot be refunded again (422);
  - after the reissue it leaves the queue and coverage is restored.
- I10 [M] Two partials complete a line, then the earlier one fails: the line stays `refunded`, the
  order is `partially_refunded`, and the reissue restores `refunded`.
- I11 [M] Void:
  - a pending partial refund → voided, out of the queue, its balance freed, statuses recomputed;
  - voiding a settled refund → 409;
  - voiding a refund whose line is already `refunded` → 409 (per Q2).
- I12 [M] Mixed (SRS mandatory), each asserting line states, balances and the order status:
  - STL refunded while the physical line is delivered → `partially_refunded`;
  - the physical line refunded after delivery while the STL is `awaiting_delivery` → `partially_refunded`,
    with the STL still queued;
  - both refunded across two refunds → `refunded`;
  - a failed refund in a mixed order → owed and `partially_refunded`.
- I13 [M] Mixed: the STL is refunded first (payment `partially_refunded`), then the physical line goes
  start → ready → shipped → delivered, none refused by BR-148.
- I14 [M] STL: mark-delivered after a partial refund works; after a full refund → 409
  `line_closed` (moved from VS-023b). A customer whose STL was fully refunded can buy it again,
  including while that refund is owed.
- I15 [M] Late capture:
  - a late success after expiry creates exactly one `late_capture` refund (no items, no requester,
    the captured amount), and the order status is unchanged;
  - two distinct provider events create one refund;
  - an overpayment refund above `amount_cents` is accepted;
  - a failed late_capture is reissued as late_capture.
- I16 [M] Backfill migration: idempotent, batched, malformed audit rows skipped and reported,
  and a downgrade that deletes only its own pending rows. The cases (a)–(h) are in §4.3.
- I17 [M] Chargeback:
  - recorded, never in the queue;
  - with a pending $10 goodwill refund on a $50 payment, charged $50 → the goodwill is voided,
    applied 50 and excess 0, so total payout ≤ 50 (Must-resolve 2);
  - after a full settled refund, charged $50 → applied 0 and excess 50, recorded with an alert
    (Must-resolve 3);
  - a cash payment → 422; a duplicate dispute reference → 409; a replay → the same 201.
- I18 [M] A chargeback covering an `in_production` physical line → the line is `cancelled` in the
  same transaction, a later `→ ready_to_ship` → 409 `line_closed`, and no refund is created
  (Must-resolve 4). A `returned` or `shipped` line covered in full: `returned` becomes `refunded`,
  `shipped` becomes `cancelled`.
- I19 [M] A chargeback on a late-captured payment voids the late_capture refund, and leaves a
  remainder refund when it is partial.
- I20 [M] Cash-block search writes a `cash_block.searched` audit row with no phone and no hash.
  The test scans `before_data`/`after_data` for the normalised phone and its `hash_phone` value.
- I21 [M] The customer `OrderDetail` refund summary: shown kinds, status mapping, chargebacks
  hidden (per Q9). Another customer → 404.
- I22 [M] (Q5 decided) The record-capture route: mismatch → late capture plus refund; a matching
  amount → 409 `use_confirm`; a status-API provider → 409; a replay returns the same 201.
- I23 [M] **`ck_chargebacks_online_only`, refused case.**
  - A direct INSERT into `chargebacks` with `payment_provider = 'cash'` against a cash payment →
    `IntegrityError` whose `constraint_name == "ck_chargebacks_online_only"`.
  - A direct INSERT with `payment_provider = 'mock'` against a cash payment fails on
    `fk_chargebacks_payment` (the column cannot lie).
  - The API on a cash payment → 422 `CHARGEBACK_NOT_ONLINE`, with nothing written.
- I24 [M] **`uq_chargebacks_dispute`, refused case.**
  - A second direct INSERT with the same `(payment_provider, provider_dispute_reference)` →
    `IntegrityError` with `constraint_name == "uq_chargebacks_dispute"`.
  - The API with a new `Idempotency-Key` and the same dispute reference → 409 `CHARGEBACK_DUPLICATE`.
  - The same reference on another provider is accepted.
- I25 [M] **Void:**
  - an admin-only route: a customer gets 404 and an admin without MFA gets 401 (also in S1);
  - a missing or empty `reason` → 422;
  - a pending refund → 200 `voided`, with exactly one `refund.voided` audit row holding the reason;
  - a second void (any reason) → 200 with the original reason, still one audit row;
  - a settled refund → 409 `already_settled`, unchanged;
  - an owed refund → `voided`, which leaves the queue;
  - reissue of a voided refund → 409 `not_failed`, with no new row;
  - a direct `UPDATE refunds SET status = 'voided', voided_at = now(), void_reason = 'x'` on a
    settled row → `IntegrityError` with `ck_refunds_void_never_settled`.
- I26 [M] Q-1 and the PR A migration: the precheck and the order of operations (§4.2a test).

### 6.3 Concurrency (`tests/concurrency/test_refund_races.py`)
- R1 [M] Concurrent partial refunds whose sum exceeds the paid amount, online and cash: exactly
  the ones that fit succeed (barrier, 20 runs), and Σ never exceeds paid.
- R2 [M] Two concurrent partial refunds that together equal the full amount: both succeed, and the
  order is `refunded`.
- R3 [M] The same `Idempotency-Key` in parallel: one row, one 201, the other a replay or 409 in-progress.
- R4 [M] A refund racing mark-delivered on one STL line. Exactly one order of events is
  committed, with no deadlock:
  - refund first (full) → the delivery is 409 `line_closed`;
  - delivery first → the refund succeeds on a `delivered` line.

  Repeated 50 times.
- R5 [M] A refund racing the cash handover on the same order: before → 409 `ORDER_NOT_PAID`, after →
  success; never a refund on an unpaid order.
- R6 [M] Settle racing fail on one refund: exactly one wins, and the other is 409.
- R7 [M] Two concurrent reissues: one new refund (UNIQUE `reissue_of_refund_id`).
- R8 [M] A chargeback racing a refund create on the same payment: the payout invariant holds in
  both orders.
- R9 [M] A late capture (Tx B) racing the backfill or a second event: one live late_capture refund.
- R10 [M] A refund racing a physical transition and a handover on another line: no deadlock, and the
  final status is correct.

These four races run on real Postgres with the `meet_or_fail` barrier, 50 runs each. Both
commit orders are forced by holding the first transaction at a barrier after its `orders` lock.
Every run asserts the invariants below, and that there is no `DeadlockDetectedError`.
- Invariant M (money): settled + pending + owed + chargeback applied ≤ paid on the payment.
- Invariant Q (queue): every refund is in exactly one of: queue (pending, or owed),
  settled, voided, or failed-and-reissued.

- R11 [M] **Chargeback vs settle** on a payment with one pending $10 refund (paid $50, charged $50):
  - settle first → the refund is `settled` and the chargeback sees it as counted: applied 40,
    excess 10, alert raised;
  - chargeback first → the refund is `voided` (absorbed), applied 50, excess 0, and the settle
    gets 409 `not_pending`.
  - Both orders: M holds, and the refund is never both settled and voided.
- R12 [M] **Chargeback vs reissue** on a payment with one owed (failed) $10 refund:
  - reissue first → the new pending refund is voided by the chargeback, and the failed one keeps
    `reissued_at`;
  - chargeback first → the failed refund is `voided`, and the reissue gets 409 `not_failed`.
  - Both orders: no live obligation remains, and M holds.
- R13 [M] **Refund create vs chargeback** on the same payment (paid $50; a create for $30 and a
  charge for $50):
  - create first → the chargeback voids it (applied 50);
  - chargeback first → the create gets 422 `REFUND_EXCEEDS_AVAILABLE` (balance 0).
  - Both orders: M holds, and total payout ≤ $50.
- R14 [M] **Void vs settle** on one pending refund:
  - void first → the settle gets 409 `not_pending`;
  - settle first → the void gets 409 `already_settled`.
  - Exactly one wins; a settled refund is never voided (the CHECK is the backstop).

### 6.4 Lock order (`tests/concurrency/test_refund_lock_order.py`, `tests/unit/…`)
- LO1 [M] A static test: every refund, chargeback and late-capture use case calls `orders.lock`
  before `payments.lock*` before `refunds.lock`/INSERT. This uses AST order checks in the style
  of `tests/unit/payments/test_cash_payment_writers.py`.
- LO2 [M] Runtime: `pg_locks` sampled inside each path (create, settle, fail, reissue, void,
  chargeback, late capture) shows the relation lock acquisition order orders < order_items <
  payments < refunds.
- LO3 [M] A deadlock hunt: 200 mixed random operations (refund, settle, fail, reissue, transition,
  handover, mark-delivered, late capture) on 3 orders with 4 workers → zero
  `DeadlockDetectedError`.

### 6.5 Security and contract
- S1 [M] Extend `VS029_ROUTES`-style lists in `tests/integration/test_openapi_security.py:110-137`
  and the boundary matrix (`tests/integration/identity/test_vs011_admin_boundary.py:65-73`) with
  `/api/v1/admin/refunds`, `/api/v1/admin/chargebacks` and the order sub-routes:
  - a customer gets 404;
  - an admin without MFA gets 401;
  - a write without CSRF gets 403;
  - a hostile body is never a 500.
- S2 [M] A leak scan: no refund or chargeback response, audit row, log line or outbox payload contains
  a phone, phone hash, address or provider reference. This extends
  `tests/security/test_contact_phone_never_leaks.py`.
- S3 [M] There is no provider refund call: `PaymentProviderPort` (`src/app/payments/application/ports.py:57-75`)
  has no refund method, and a test asserts it.
- S4 [N] The rate limits per admin: the 61st write in an hour → 429.

### 6.6 Smoke and e2e
- E1 [M] `tests/e2e/test_vs030_refunds.py`: paid mixed order → partial refund → settle → second
  refund → fail → reissue → settle. The queue is empty, and the order and payment are `refunded`.
- E2 [M] `tests/smoke/test_vs030_smoke.py`: the routes exist, the migration applies, and the
  obligations index exists.

### 6.7 Running the suite
Sequential chunks, as in VS-024 §6.7: `tests/unit`, then `tests/integration/payments`,
`…/ordering`, `…/fulfillment`, then `tests/concurrency` alone, then security, e2e and smoke.
Never everything at once (memory, VS-041 audit §8).

---

## 7. Docs and ADRs

- **ADR-042 "Refunds, voids and chargebacks"** (new; re-check the number). It records:
  - D1 (the status reorder; the VS-023 note at `docs/vertical-slice-plan.md:793` asks for a
    confirmation, which the owner gave, working alone; Revision 2);
  - D2 (`voided`);
  - D3 (separate chargeback tables; this amends ADR-024 d16 and SRS §9.7);
  - D4 (cancel in the chargeback transaction);
  - D5;
  - D6 (proof of the two cash properties);
  - D10, and the VS-024 Q2 decision.

  It amends ADR-024 d12 and d16 and ADR-036 d7 (record-capture, Q5). **It states explicitly
  that it amends SRS §20.2** (and database-design §17.2), listing D-a and D-c as the only
  behaviour changes and citing U15 (§3.1a).
- **SRS:**
  - §20.1: add the payment back edges.
  - §20.2: the new order (owed first; "all lines refunded" removed).
  - §9.6: create → pay → settle (appendix `:111`); the FR-10 cap includes the reserved failed
    amount (`:112`); the wording "a `shipped` line after it comes back" becomes "refunded from
    `returned`" (`:114`).
  - §9.7: separate chargebacks, void absorption, the late-capture chargeback.
  - §10.3–10.4 and BR-064: the partial-refund nuance (`:113`).
- **database-design:**
  - §9.3: add `voided` and the new columns, and remove `kind = chargeback` and `excess_cents`.
  - §9.4: the composite FKs.
  - New §9.5 `chargebacks` and §9.6 `chargeback_items`.
  - §17.2: the new projection.
  - §19.9: unchanged.
  - The indent fix at §17.4 is VS-031's.
- **api-endpoints:**
  - §19: the void, chargebacks and record-capture rows; the reissue key; error codes
    `ORDER_NOT_PAID`, `ORDER_TOTAL_MISMATCH`, `CHARGEBACK_*`; the obligations queue includes
    owed refunds (`:110` appendix).
  - §29.13: the schemas.
- **entities-and-business-rules** and **domain-glossary:** "voided", and chargeback as its own record.
- **`docs/refunds.md`** (new): the as-built reference, the late-capture listing replacing
  `checkout.md`'s SQL (`docs/vertical-slice-plan.md:567`), and the runbook for "create → pay
  in dashboard → settle".
- **`docs/order-history.md:42`, ADR-033 d7:** the refund summary as built.
- **`docs/frontend-handoff/openapi.json` and `BACKEND-RESPONSE.md`:** the new routes.
- **Slice plan:**
  - VS-030 Status;
  - VS-032 "Depends on" gains VS-031 (Must-resolve 5), and its chargeback bullet (`:929`)
    points to ADR-042;
  - VS-031 gains the §3.7 interface;
  - the six Must-resolve items are marked resolved, with links;
  - the README slice table.

---

## 8. Implementation steps, in order, with checkpoints

### PR A: schema only (branch `vs-030-schema`, merged first)
1. Re-derive the head and re-check the ADR number.
2. Migration §4.2 and the ORM models (`app.payments.infrastructure.models`: `RefundModel`,
   `RefundItemModel`, `ChargebackModel`, `ChargebackItemModel`; the new uniques in
   `app.ordering.infrastructure.models` and `payments` models).
3. Schema tests: every CHECK, FK, unique and partial index (including the refused cases of
   I23, I24 and the void CHECKs of I25 at INSERT/UPDATE level), round-trip upgrade, downgrade
   and upgrade, the Q-1 precheck and order of operations (§4.2a, I6, I26), and one head.
4. A short ADR-042 draft recording D3 (it shapes the schema).
5. **PR A merges alone** and is migrated on staging before PR B branches. No code in PR A reads or
   writes the new tables (§4.2a).

**CP1** (end of PR A): migration applied on a copy, the schema tests green, a single head.
Reports: the head, the constraint list, and the downgrade result.

### PR B: refund core (branch `vs-030-refund-core`, from main after PR A)

Owner decisions at PR B's start (2026-10-23):
- The branch is `vs-030-refund-core`, not the `vs-030-refunds` first planned here.
- ADR-042 stays **Proposed** in PR B, which only appends its decisions. PR C sets it Accepted.
- PR B's paths lock in ranks 0-4 only (claim, `orders`, lines by id, `payments`, `refunds`), then
  6-7 (cart and phone lock). Rank 5 (`chargebacks`) is reserved for PR C, and the code says so.
1. The pure rules (§3.1, §3.2) with U1–U12.
2. Ordering: the `RefundFacts` signature, `refund_lines`, the stop-gap removal, the strict-xfail
   conversion (one commit, named), and the allow-lists.
3. The refund store, the use cases (create, settle, fail, reissue, void), the routes, idempotency,
   the email and notification, the admin detail, the customer summary, and the cash-block search audit.
4. The integration, concurrency, lock-order, security, e2e and smoke tests for these paths.

- **CP2** (after B2): the full unit suite plus `tests/integration/fulfillment` green with the
  rewritten stop-gap tests. Reports: the diff of the three call sites.
- **CP3** (end of PR B): every [M] in §6 that does not need chargebacks or late capture is green,
  including U15 and U16. Reports: the race results (R1–R7, R10, R14), LO1–LO3, and U15's
  per-class counts.

### PR C: late capture, chargebacks, cleanup (branch `vs-030-late-capture-chargebacks`)
1. The `SqlLateCaptureRefunds` binding (§3.5) plus I15 and R9.
2. The backfill migration (§4.3) plus I16.
3. Chargebacks (§3.3) plus I17–I19, I23, I24, U13, R8 and R11–R13.
4. Record-capture (Q5) plus I22.
5. The docs and ADR-042 final (§7); the VS-032 dependency.

- **CP4:** the full sequential suite (§6.7) green. Reports the counts and any skips.
- **CP5:** the slice status set to Done, and the docs merged.

**Why this split:** PR A carries all DDL, so the later PRs need no lock-sensitive migration
except PR C's data step. PR B is the money core the queue depends on, and is reviewable on
its own. PR C gathers the paths that hook into VS-024's code (`apply.py`, `verification.py`) and
the VS-032-facing chargebacks, so a delay there does not block refunds.

### 8.1 Lock order per path (proof of no cycle)

**Ranks.** Every lock any path takes has a rank, and within a rank, rows are taken in
ascending `id`:

| Rank | Resource | How it is taken |
|---|---|---|
| 0 | `idempotency_records` row `(scope, user_id, key)` | INSERT of the claim; a rival with the same key waits on the unique index (`src/app/platform/application/ports/idempotency.py:13-24`) |
| 1 | `orders` row | `SELECT … FOR UPDATE` (`src/app/ordering/infrastructure/orders.py:190-196`) |
| 2 | **every** `order_items` row of that order, by id | `FOR UPDATE … ORDER BY id` (`orders.py:198-204`, via `lock_order_for_change`, `src/app/ordering/public.py:152-158`) |
| 3 | `payments` rows of that order, by id | `lock_for_order`, `FOR UPDATE ORDER BY id` (`src/app/payments/infrastructure/payments.py:182-186`), or `lock(payment_id)`; or the INSERT of a payment |
| 4 | `refunds` rows of that order, by id | `FOR UPDATE ORDER BY id`, or INSERT (unique-index waits) |
| 5 | `chargebacks` | INSERT only (unique-index wait on `uq_chargebacks_dispute`) |
| 6 | the customer's `carts` row | VS-031 cash refusal and checkout only |
| 7 | the cash phone advisory lock | `pg_advisory_xact_lock` (`src/app/ordering/infrastructure/cash.py:28-32`) |

**The nine paths** (as asked), then every other writer of the same tables:

| # | Path | Lock sequence (ranks) | Reads made without a lock, after rank 1 | Evidence |
|---|---|---|---|---|
| 1 | **Refund create** (`POST …/orders/{id}/refunds`) | 0 claim → 1 → 2 (all lines) → 3 (all the order's payments, by id) → 4 INSERT `refunds` + `refund_items` → line `UPDATE`s (already rank 2) → payment `UPDATE` (already rank 3) → recompute `orders.status` (already rank 1) → claim `complete` (already rank 0) | refund and chargeback rows of the order (stable: every writer holds rank 1) | §3.3 |
| 2 | **Settle** | an unlocked read of the refund (to learn `order_id`) → 1 → 2 → 3 (the refund's payment) → 4 `FOR UPDATE` that refund → re-check its `order_id` → UPDATE. No recompute. | none | §2.3; the pattern of `apply.py:46-52` |
| 3 | **Fail** | as 2 → UPDATE → payment UPDATE (rank 3, held) → recompute (rank 1, held) | the order's other refunds and chargebacks | §2.3 |
| 4 | **Reissue** | 0 claim → an unlocked read → 1 → 2 → 3 → 4 `FOR UPDATE` the failed refund → INSERT the new refund + items (unique wait on `uq_refunds_reissue_of`, same order so already serialised at rank 1) → recompute → `complete` | as 3 | §2.4 |
| 5 | **Late capture** (Tx B of verification, manual confirm or record-capture) | an unlocked read of the payment → 1 → 2 → 3 `lock(payment_id)` → payment UPDATE → 4 INSERT the `late_capture` refund (`ON CONFLICT` on `uq_refunds_one_live_late_capture`); no recompute | none | `apply.py:46-52`, `:172-207`; `verification.py:59`; §3.5 |
| 6 | **Chargeback** | 0 claim → 1 → 2 → 3 `lock(payment_id)` → 4 `FOR UPDATE` every pending and owed refund on that payment, by id → their UPDATEs to `voided` → 5 INSERT `chargebacks` + items (unique wait on `uq_chargebacks_dispute`) → line UPDATEs (rank 2, held) → payment UPDATE → recompute → `complete` | refunds and chargebacks of the order | §3.3 |
| 7 | **Cash handover** (VS-029) | 1 → 2 → 3 INSERT the cash payment (`uq_payments_one_cash` wait, same order) → line UPDATEs → recompute | refund facts (`NO_REFUNDS` by construction, §3.4) | `src/app/fulfillment/application/record_cash_handover.py:38-49`; `src/app/ordering/public.py:374-416` |
| 8 | **Cancel by VS-031** (self or admin) | 1 → 2 → 3 (`create_refund` locks the payment) → 4 INSERT the `cancellation` refund → line UPDATEs → (whole-order cash refusal only) 6 the customer's cart → 7 the phone lock → INSERT the block → recompute | balances (§3.7) | ADR-024 d9 `docs/adr/ADR-024-…md:31`; §3.7 |
| 9 | **VS-029 transitions** (physical edge; STL mark-delivered, VS-023b) | 1 → 2 → line UPDATE → recompute | `reached_paid` and refund facts from `payments`/`refunds`, plain reads (`transition_line.py:60-61`: "every payment writer locks the order first") | `src/app/fulfillment/application/transition_line.py:36-61`; `src/app/ordering/public.py:258-355` |

Other writers of these tables, for completeness:

| Path | Lock sequence | Evidence |
|---|---|---|
| Void | as 2 (`FOR UPDATE` the refund at rank 4) → UPDATE → payment UPDATE → recompute | §2.3 |
| Backfill (PR C migration) | rank 4 INSERT only (`ON CONFLICT DO NOTHING`); it never locks 1–3. A wait on the unique index can only be behind a path-5 transaction, which never waits on the backfill's locks, because the backfill holds only its own inserted index entries. | §4.3 |
| Cart checkout, online or cash (VS-028) | 0 → 6 → (address `FOR SHARE`) → 7 → INSERT order, lines and payment. It never touches ranks 1–5 on an **existing** row; its new rows are invisible until commit. | ADR-024 d9 `:37`; `src/app/ordering/api/checkout.py:302-375` |
| Payment retry, release, reconciliation (VS-024) | 1 → (2) → 3 → recompute; batch selection takes no lock | ADR-024 d9 `:35-36`, `:39` |

**Proof of no cycle:**
1. **Monotone acquisition.** In every row of both tables, a transaction requests ranks in
   non-decreasing order. Within one rank it requests rows in ascending `id`
   (`ORDER BY id … FOR UPDATE` at ranks 2, 3 and 4). Rank 0 is requested only first. Ranks 6
   and 7 are requested only after every rank ≤ 5 lock the transaction will ever take (path 8),
   or with no rank 1–5 lock on an existing row at all (checkout).
2. **Unlocked pre-reads take no lock.** Paths 2–5 read the refund or payment once without a
   lock, only to learn `order_id`. The decision is re-made on the rows read after rank 1, and a
   refund or payment that moved order is refused.
3. **Updates inside held ranks add no edge.** Every UPDATE or INSERT after rank 1 hits a row
   this transaction already locked (lines, the payment, the refunds) or a new row. The only new
   waits are unique-index waits at ranks 0, 3, 4 and 5:
   - rank 3 (`uq_payments_one_cash`) and rank 4 (`uq_refunds_one_live_late_capture`,
     `uq_refunds_reissue_of`) are keyed by one order's payment or refund, so both contenders
     already hold or wait for that order's rank-1 lock and are serialised there;
   - rank 5 (`uq_chargebacks_dispute`) may involve two orders, but the waiter holds ranks
     ≤ 4 of its own order and the holder needs nothing more after rank 5 except its commit.
4. **Hence:** order all lock requests by (rank, id). A wait edge T1 → T2 exists only when T1
   requests a resource that T2 holds, and by 1 that resource is strictly above every resource
   T1 holds. Along any wait path, the highest held resource strictly increases. A cycle would
   need it to return to its start, which is impossible in a total order. ∎
5. **The deadlock ADR-024 warns about** (a line locked before its order, against the handover)
   cannot occur: no path locks rank 2 without rank 1 first. `test_order_item_writers.py`
   enforces this for line writers, and U12 for refund writers.

LO1 (static order), LO2 (`pg_locks` sampling per path) and LO3 (a random mixed workload with
zero `DeadlockDetectedError`) test it, together with R1–R14.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| The status reorder changes existing behaviour (cases A, B) | Only reachable once refunds exist (VS-030). ADR-042 plus the owner's Q1 answer (Revision 2); U1 and U2 pin it. |
| VS-031 later adds an edge out of `delivered`/`picked_up` and silently breaks the cash count | U5 fails loudly and names `open_order_count`. |
| Voiding on chargeback drops a legitimate goodwill refund | The audit lists the voided ids. The admin re-creates any still-due refund within the new balance. Q3. |
| A late capture with no reported amount creates an obligation at the attempt amount | Manual payment: the admin checks the dashboard first, and can void. Q6. |
| Production `order_items.user_id` mismatches make the migration fail | The precheck raises with a count. The data is fixed by hand under the owner's eye, never automatically. |
| VS-029b merges first with its own migration | Re-derive the head before `alembic revision` (header). |
| `record-capture` typos | The obligation is manual; void exists; audited. Q5 lets the owner refuse it. |
| A voided full refund on a `refunded` line would leave a line `refunded` with balance owed back to the business | Refused (409) per Q2. |
| Customers confused by owed refunds shown as pending | The summary maps `failed` → "processing" (Q9). |

---

## 10. Owner questions (each with a recommendation)

**All twelve answered on 2026-10-23, as recommended** (see Revision 1, with the Q6 and Q8
precisions). The text below is kept as asked.

1. **Status order (Must-resolve 1).** Owed refund → `partially_refunded` checked before
   all-cancelled and both refunded rules, and "all lines refunded" dropped.
   *Recommend:* yes. ADR-042 records it (decided by the owner; no co-developer, Revision 2).
2. **Voiding.** A `voided` refund status with `POST /refunds/{id}/void` (pending or owed only,
   reason required). It is refused when any of the refund's lines is already `refunded`.
   *Recommend:* yes, with that restriction. A full mistaken refund is corrected by
   settling or failing it, not by voiding it.
3. **Chargeback absorption (Must-resolve 2).** Recording a chargeback voids every pending and owed
   refund on that payment, and the admin re-creates any still-due refund.
   *Recommend:* yes. It is the simplest rule that guarantees payout ≤ paid.
4. **Chargebacks in VS-030** (PR C, manual route; separate tables, Must-resolve 3) rather than
   VS-032. *Recommend:* yes, because the balance rules are shared. VS-032 then only wires provider
   disputes. VS-031 is added to VS-032's dependencies (Must-resolve 5).
5. **VS-024 Q2: record-capture** for no-status-API providers (mismatch only), creating a late-capture
   obligation. *Recommend:* yes, in PR C. The alternative leaves such money outside the queue
   and BR-126.
6. **A late capture with no reported amount** creates the obligation at the attempt amount (flagged
   in the reason), and a non-USD captured currency is stored as reported.
   *Recommend:* yes. Never lose an obligation.
7. **Emails.**
   *Recommend:* "refund issued" (email plus notification) at creation for `admin` and
   `cancellation`; for `late_capture`, one at settlement only; nothing on fail, reissue or void.
8. **The cash-block search audit** records no phone and no hash (only the filters, result count and
   block ids). The #34 wording says "phone hash only".
   *Recommend:* no hash, per ADR-038 (the hash never reaches a read surface, and the audit
   viewer is one).
9. **The customer refund summary.**
   *Recommend:* list `admin`, `cancellation` and `late_capture` refunds, with status shown as
   "processing" (pending or failed) or "refunded" (settled); voided and chargebacks hidden.
10. **`Idempotency-Key` required on reissue and chargebacks** (api-endpoints lists it for create only).
    *Recommend:* required on both.
11. **The Q-2 mismatch response.**
    *Recommend:* 409 `ORDER_TOTAL_MISMATCH`, plus an error log and a `payment` alert, with nothing
    written (admin-only, so naming it leaks nothing).
12. **The open-cash count (Must-resolve 6).**
    *Recommend:* keep the status-based count with the P1 and P2 proofs and tests (no new index);
    revisit only if U5 ever fails.
