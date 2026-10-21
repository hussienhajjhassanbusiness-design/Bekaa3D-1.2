# VS-023b — STL Delivery Queue and Mark-as-Sent: Implementation Plan

**Status:** DONE (2026-10-21), see [ADR-039](../adr/ADR-039-stl-delivery-workflow.md). Branch `vs-023b-stl-delivery`.
**Owner decisions (2026-10-21):**
- Q1 yes, as a thin interface only: `fulfillment` owns routes and the use case; no `order_items` SQL moves out of `ordering`.
- Q2 the interim `OrderItemTransitionRead` response stands; VS-029 replaces it with `AdminOrderDetail`.
- Q3 payment time only if a paid timestamp sits on the line or order. None does (`verified_at` is on `payments`, `payments/infrastructure/models.py:59`), so the queue orders by placement time (`order_items.created_at`).
- Q4-Q10 as recommended in §10.
**Date:** 2026-10-21
**Planned against:** `main` at `ab3ee0c` (merge of PR #27, VS-028 PR A).
**Planned against alembic head:** `fcd589e89e59` (`cash_payment_blocks_and_cash_settings`, VS-028 PR A).
- Derived statically from `revision` / `down_revision` in `migrations/versions/*.py`: one linear chain, and no file names `fcd589e89e59` as its `down_revision`. This slice's migration therefore has `down_revision = "fcd589e89e59"`.
- Re-derive the head immediately before `alembic revision`: VS-028 PR B, VS-029 and VS-030 may also add migrations.

**Pre-flight (2026-10-21):** `git fetch`, `git checkout main`, `git pull --ff-only` (already up to date). `git branch -r` shows no branch mentioning VS-023b, delivery, STL queue or fulfillment. Highest ADR on `origin/main`: **ADR-038**, so this slice's ADR is **ADR-039** (re-check before writing it). Last five commits: `ab3ee0c`, `15c3c2f`, `93268a0`, `7003f8c`, `d3612ca`.

**Format:** follows [`VS-024-payment-recovery-plan.md`](VS-024-payment-recovery-plan.md). `file:line` references are on `main` at `ab3ee0c`. Tests are labelled **[M]** (must-have) or **[N]** (nice-to-have). The pasted request was cut off at item 5 ("The cleanup: removing"); §3.8 takes it to mean the cleanup that `docs/vertical-slice-plan.md:581-582` already lists.

---

## 0. Decisions this plan takes (summary)

1. **Column naming is `fulfilled_at`, not `delivered_at`.** The code has `order_items.fulfilled_at` (`src/app/ordering/infrastructure/models.py:253`) and `delivered_by` (`:254`); `ck_order_items_stl_delivery_record` (`:328-332`) requires both on a delivered STL line. `delivered_at` exists in no code. The VS-023b entry already says `fulfilled_at` (`vertical-slice-plan.md:582`). Doc corrections are in §7.1.
2. **No schema PR first.** Both columns and all CHECKs are already frozen by VS-023 (`03a4730dd046`). The one migration adds the queue index and deletes `daily_download_cap`. It is small and ships in the same PR as the code (§4).
3. **The queue index is `(created_at, id)`, partial on `product_type = 'stl' AND fulfillment_status = 'awaiting_delivery'`.** The plan text says `(created_at)` (`vertical-slice-plan.md:576`); `id` is added so keyset pagination has a total order.
4. **The transition endpoint is the one VS-029 extends.** The legal-edge table is a pure function in `ordering/domain`, so VS-029's `available_actions` (`vertical-slice-plan.md:764`) and the physical edges are added to the same table (§3.2, §6).
5. **Fulfillment owns the workflow, Ordering keeps the table.** Routes, use case and notices live in `src/app/fulfillment` (ADR-019 d8). All `order_items` SQL stays in `ordering`, behind `ordering.public`, so the writers allow-list test (`tests/unit/ordering/test_order_item_writers.py:13-21`) stays the single registry of writers (ADR-039, §7.2).
6. **Email goes through the outbox in the same transaction.** `dispatch_outbox` (`src/app/jobs/outbox.py:17`) sends later, so no transaction is held open across anything external.

---

## 1. Scope and non-goals

**In scope**
- `GET /api/v1/admin/stl-deliveries`: every STL line in `awaiting_delivery`, oldest first, keyset-paged.
- `POST /api/v1/admin/orders/{order_id}/items/{item_id}/transition` for STL lines only: `awaiting_delivery → delivered`.
- On success, one transaction writes: `fulfilled_at` and `delivered_by`, the line history row, the recomputed order status, one audit row, one in-app notification (`download`, `stl.delivered`), one outbox email.
- One migration: queue index, and deletion of the `daily_download_cap` setting.
- Cleanup: the `digital_assets` package and its test folders, the stale `VS-019` comment, the registry entry (§3.8).

**Non-goals (and who owns them)**
- Physical-line edges, `available_actions`, `AdminOrderDetail`, the admin order list: **VS-029**.
- Refunds, and the refund inputs to `derive_order_status`: **VS-030**. This slice only guarantees a refunded line is never listed or delivered (§2.3, §3.4).
- Re-sending a file, delivery undo, bulk mark-as-sent, attachments or upload of any file: out of scope (ADR-019 d1, d6).
- Customer-facing delivery view: already built in VS-025 (`order-history.md:30`, ADR-033 d6).
- A delivery SLA or reminder job for stale items: not in V1; see owner question 8.

---

## 2. API

Both routes mount in `src/app/api/v1/admin.py` next to the other admin routers (e.g. `:51`, `:92-109`), so they inherit `AdminBoundaryRoute`: anonymous → 401, customer → 404, admin without MFA → 401 `MFA_REQUIRED`. The unsafe route also takes `require_csrf`, as `admin_release.py:83` does.

### 2.1 `GET /api/v1/admin/stl-deliveries`

Query: `cursor` (opaque, `max_length=200`), `limit` (1–100, default 25), optional `product_id`, optional `customer_id` (the buyer's `user_id`).

Response `StlDeliveryPage`:

```
items: [StlDeliveryRead], next_cursor: str | null
StlDeliveryRead {
  item_id, order_id, order_number,
  product_id, product_name,          # product_name_snapshot
  customer_id, customer_email,       # orders.user_id, orders.customer_email_snapshot
  line_total_cents, currency,
  queued_at                          # order_items.created_at
}
```

- Fields deliberately not exposed: payment ids or provider references, contact phone, IP hashes, internal notes, the idempotency key, consent records. This is an admin-only route, so `customer_email` is allowed here, and it is exposed nowhere else (customers get 404 before the handler runs).
- No `customer name` field: `orders` carries no name, only `customer_email_snapshot` (`models.py:127`) and `user_id`. See owner question 4.

### 2.2 `POST /api/v1/admin/orders/{order_id}/items/{item_id}/transition`

Body `OrderItemTransitionRequest { target_status: Literal["delivered"] }`, `extra="forbid"`. Any other `target_status` is 422 for now; VS-029 widens the literal.

Success `200 OrderItemTransitionRead { order_id, item_id, fulfillment_status: "delivered", fulfilled_at, delivered_by, order_status }`. `api-endpoints.md:561` says this route returns `AdminOrderDetail`, which does not exist until VS-029; see owner question 2.

Errors:

| Case | Status | Body |
|---|---|---|
| anonymous / no MFA | 401 | `AUTH_REQUIRED` / `MFA_REQUIRED` |
| customer | 404 | `NOT_FOUND` |
| missing CSRF | 403 | `CSRF_INVALID` |
| order unknown, or `item_id` not a line of `order_id` | 404 | `NOT_FOUND` (same body for both, so existence does not leak) |
| line already `delivered` | 409 | `INVALID_STATE_TRANSITION`, `reason: "already_delivered"` |
| line `refunded` or `cancelled` | 409 | `INVALID_STATE_TRANSITION`, `reason: "line_closed"` |
| line `pending` (unpaid) | 409 | `INVALID_STATE_TRANSITION`, `reason: "not_awaiting_delivery"` |
| physical line | 409 | `INVALID_STATE_TRANSITION`, `reason: "not_an_stl_line"` (VS-029 removes this for physical edges) |
| bad body / UUID | 422 | `VALIDATION_ERROR` |
| rate limit | 429 | `RATE_LIMITED` |

There is no `Idempotency-Key`. A replay is a 409 `already_delivered`, which is the correct outcome for a second administrator and harmless for a retry (the first call already wrote everything). The 409 body carries the existing `fulfilled_at` so a retrying client can show success; it carries no `delivered_by`.

Rate limit: per-administrator hourly, via `enforce_rate_limit` as `admin_release.py:55-63`. See owner question 6.

### 2.3 Why a refunded line never appears (ADR-019 d7)

The queue filters `fulfillment_status = 'awaiting_delivery'` only. A line fully refunded becomes `refunded` (`SRS.md:1199`), so it leaves the queue by construction when VS-030 writes that status. Nothing writes `refunded` today (grep of `src/` finds no writer), so VS-023b proves the exclusion with a seeded `refunded` line (§6). A partly refunded line stays `awaiting_delivery` and stays listed, as the SRS requires.

---

## 3. Layers, function by function

### 3.1 `ordering.domain` (pure, no framework imports; `tests/unit/test_deep_architecture.py:64-68`)

New `src/app/ordering/domain/line_transitions.py`:

```python
class TransitionRefusal(StrEnum):  # the 409 `reason` values
    ALREADY_DELIVERED, LINE_CLOSED, NOT_AWAITING_DELIVERY, NOT_AN_STL_LINE


def stl_transition_refusal(
    product_type: ProductType, current: OrderItemStatus, target: OrderItemStatus
) -> TransitionRefusal | None:
    """None when (stl, awaiting_delivery -> delivered); else the refusal."""
```

It is the first row of the edge table VS-029 extends into `legal_edges(line) -> list[target]` (the source of `available_actions`). Keep it a table, not an if-chain.

### 3.2 `ordering.infrastructure.orders.SqlOrderStore` (the only module that writes `order_items`)

- `set_line_delivered(line_id, *, at, delivered_by)`: `UPDATE order_items SET fulfillment_status='delivered', fulfilled_at=:at, delivered_by=:by, updated_at=:at WHERE id=:id AND fulfillment_status='awaiting_delivery' AND product_type='stl'`; returns affected row count. The status guard in the `WHERE` is belt and braces behind the lock. `set_line_status` (`orders.py:215-226`) is **not** extended: it cannot set `fulfilled_at`/`delivered_by`, and the CHECK needs them in the same statement.
- `stl_delivery_page(*, after, limit, product_id, user_id)`: the queue query (§5). Selects `order_items` joined to `orders` on `orders.id = order_items.order_id` for `order_number` and `customer_email_snapshot`. Never `FOR UPDATE`.
- `lock_order` / `lock_lines` (`orders.py:174`, `:182`) are reused. The `lock_lines` comment (`orders.py:183-185`) already names VS-023b as a future writer; update it to say the lines lock is now **needed** by this writer's reading of the line state.
- `_LINE_COLUMNS` (`orders.py:47-60`) lacks `fulfilled_at` and `delivered_by`, and `OrderLine` has no such fields; add both to the entity so the 409 body and the response can be built from the locked row.

### 3.3 `ordering.public`

- `mark_stl_line_delivered(session, locked, *, line_id, admin_id, at) -> OrderLine`: the second `set_line_status`-class writer.
  1. Find the line in `locked.lines` (already read under `FOR UPDATE`); not found → `LineNotFoundError` (route maps to 404).
  2. `stl_transition_refusal(...)`; not None → `InvalidLineTransitionError(reason)`.
  3. `store.set_line_delivered(...)`; 0 rows → same error (cannot happen under the lock; defensive).
  4. `store.add_history([StatusChange(order_id, "awaiting_delivery", "delivered", order_item_id=line_id, actor_user_id=admin_id)])`.
  5. `recompute_order_status(...)` with the line states updated in memory, `actor_user_id=admin_id` (`public.py:84-110`). `payment_reached_paid=True` is correct: a line is `awaiting_delivery` only after verification (`mark_order_paid`, `public.py:115-150`).
  6. Return the updated line.
- Refund inputs: `OrderStatusInputs.refunds_cover_paid` and `refund_present` default False "until VS-030 computes them" (`order_status.py:25-27`). Delivering the only line of a partly refunded order must not flip it from `partially_refunded` to `completed`. Stop-gap, in a helper `status_inputs_for(locked, line_states)`: set `refund_present=True` when `locked.order.status` is already `PARTIALLY_REFUNDED`. VS-030 replaces the helper body with the real refund query; both slices call the helper, never build `OrderStatusInputs` by hand.
- `stl_delivery_page(...)`: pass-through to the store, returns domain rows (frozen dataclass `StlDeliveryRow`).
- Both added to `__all__` (`public.py:40-66`).

### 3.4 `fulfillment` (new content in the empty package)

`src/app/fulfillment/application/mark_stl_delivered.py` and `…/ports.py`:

```python
async def mark_stl_delivered(session, *, order_id, item_id, admin_id, request_id, ip_hash, now) -> DeliveryResult
```

Order of operations, one transaction (the route's session, committed by the dependency, as `release_order_by_admin` does):
1. `locked = await lock_order_for_change(session, order_id)` — orders `FOR UPDATE`, then every line `FOR UPDATE` by id (ADR-024 d9, `public.py:76-83`). `None` → 404.
2. `line = mark_stl_line_delivered(session, locked, ...)`. This re-reads state **after** the lock, so a racing refund (VS-030) or a second administrator sees the committed result, never a stale one.
3. `audit.record(actor_user_id=admin_id, action="stl.delivered", entity_type="order_item", entity_id=item_id, before_data={"fulfillment_status": "awaiting_delivery"}, after_data={"fulfillment_status": "delivered", "fulfilled_at": ..., "delivered_by": ..., "order_id": ..., "order_number": ...}, request_id, ip_hash)` through `SqlAuditWriter` (`app.platform.public`).
4. `notices.stl_delivered(locked.order, line)`:
   - `SqlOutboxWriter(session).add(user_id, recipient_email=order.customer_email_snapshot, template="order_stl_delivered", payload={order_id, order_number, item_id, product_name})` (pattern: `SqlPaymentNotices.payment_confirmed`, `payments/infrastructure/ordering_side.py:70-90`).
   - `create_notification(session, user_id, NotificationType.DOWNLOAD, payload={"event": "stl.delivered", "order_id", "order_number", "item_id", "product_name"})` (`engagement/public.py:33`).
5. Return the result; the route builds `OrderItemTransitionRead`.

Nothing in the transaction calls the email provider, the network, or storage. The notification is a row; the email is a row; `dispatch_outbox` (every minute, per-message transaction, `outbox.py:34-50`) does the sending.

`src/app/fulfillment/infrastructure/` holds `SqlStlNotices` only; no SQL on `order_items`.

### 3.5 `fulfillment.api`

- `stl_deliveries.py`: `admin_router = APIRouter(prefix="/stl-deliveries", route_class=AdminBoundaryRoute)`; handler `list_stl_deliveries`. `encode_cursor` / `decode_cursor` for `(created_at, id)` follow `payments/api/admin_payments.py:365-385` (aware datetime required, anything else 422 on `cursor`).
- `item_transition.py`: `admin_router = APIRouter(prefix="/orders", …)`; handler `transition_item`. Maps `LineNotFoundError`/`OrderNotFoundError` → `not_found_error()`, `InvalidLineTransitionError` → `ApiError(409, "INVALID_STATE_TRANSITION", extensions={"reason": ...})` exactly as `admin_release.py:105-117`. Two routers share the `/orders` prefix (`admin_release.py:36` already does); FastAPI allows it, but the route-walk test (`tests/integration/identity/test_vs011_admin_boundary.py:395`) must be re-run.
- Cross-context imports only through `*.public` (rule at `test_deep_architecture.py:1-9`); `app.api.*` is a composition root and may wire the adapters.

### 3.6 Concurrency design

| Race | Mechanism | Outcome |
|---|---|---|
| Two administrators mark one line | `orders` `FOR UPDATE` serialises; the loser re-reads the line as `delivered` under the lock | one 200, one 409 `already_delivered`; one audit row, one outbox row, one notification |
| Mark-sent vs refund (VS-030) | both take the `orders` lock first (VS-030 plan at `vertical-slice-plan.md:36`: "exactly one wins") | the winner commits; the loser sees `refunded` / `delivered` and gets 409 |
| Mark-sent vs payment verification | `mark_order_paid` holds the same lock; a `pending` line is refused | 409 `not_awaiting_delivery` |
| Queue read during the above | plain read, no lock | may show a line that was delivered a moment ago; harmless, the POST decides |

### 3.7 `jobs` / worker

No new job. `dispatch_outbox` already runs every minute. Template name `order_stl_delivered` is a string; the provider takes it as-is (`grep order_payment_confirmed` finds it only in `ordering_side.py` and tests, so there is no registry to extend; the console provider prints it).

### 3.8 Cleanup (deletions)

Evidence from a fresh grep on `main`:
- `src/app/digital_assets/` (`__init__.py` + four empty layer packages), `tests/unit/digital_assets/__init__.py`, `tests/integration/digital_assets/__init__.py`: delete.
- `tests/unit/test_deep_architecture.py:21` lists `"digital_assets"` in `CONTEXTS`: remove it (otherwise `test_every_context_exists` at `:60-61` fails once the directory is gone).
- `src/app/jobs/partitions.py:12`: docstring "VS-019 adds `downloads` here." — delete the sentence. This is the **only** `VS-019` text in `src/` and `tests/`.
- `vertical-slice-plan.md:581-582` also names `identity/api/admin_users.py`. A grep of that file for `VS-019|digital_assets` finds nothing, so that reference is already clean: **UNVERIFIED that anything remains there**; the implementer re-greps and drops the claim from the plan entry.
- `src/app/platform/domain/settings_registry.py:155-165`: delete the `daily_download_cap` `SettingDefinition`.

---

## 4. Database

**Does a schema PR merge first?** No. `fulfilled_at`, `delivered_by`, `ck_order_items_stl_delivery_record`, `ck_order_items_physical_no_delivered_by`, `ck_order_items_status_by_type` and `uq_order_items_stl_ownership` all exist (`models.py:253-254`, `:327-342`, `:350-359`). The slice is one PR with one small migration. (VS-024 and VS-028 split schema PRs because they added columns; this adds none.)

**Migration** `migrations/versions/<new_id>_stl_delivery_queue_index.py`, `down_revision = "fcd589e89e59"`:

```python
def upgrade() -> None:
    op.create_index(
        "ix_order_items_stl_awaiting",
        "order_items",
        ["created_at", "id"],
        postgresql_where=sa.text(
            "product_type = 'stl' AND fulfillment_status = 'awaiting_delivery'"
        ),
    )
    op.execute(_settings.delete().where(_settings.c.key == "daily_download_cap"))


def downgrade() -> None:
    # Restored exactly as de1d8a23512f seeded it (type integer, value 20, same description).
    op.execute(
        postgresql.insert(_settings)
        .values([_DAILY_DOWNLOAD_CAP])
        .on_conflict_do_nothing(index_elements=["key"])
    )
    op.drop_index("ix_order_items_stl_awaiting", table_name="order_items")
```

- Pattern for the settings delete and its downgrade re-seed: `migrations/versions/fcd589e89e59_…py:57-63`, `:173`, `:178-182`. Copy the original seed row (type, value, description, minimum/maximum) from `de1d8a23512f` and `settings_registry.py:155-165` **before** deleting the registry entry.
- Also declare the same index in `OrderItemModel.__table_args__` (`models.py:343-360`) so autogenerate stays clean.
- Existing test to flip: `tests/integration/ordering/test_order_payment_schema.py:799-810` (`test_the_stl_delivery_queue_index_is_left_to_vs023b`) asserts that no index but `uq_order_items_stl_ownership` mentions `awaiting_delivery`. Replace it with a test that `ix_order_items_stl_awaiting` exists, is partial on the exact predicate, and is not unique. The non-unique-index inventory just above it (`_NON_UNIQUE_INDEXES`, `:795`) gains the new name.
- `ix_order_items_physical_status` (`models.py:344-349`) is physical-only and does not serve this query.
- Backfill: none. The index is built over existing rows; a few hundred `awaiting_delivery` lines at most. A plain `CREATE INDEX` is fine; `CONCURRENTLY` is not needed on a table this small and would force an autocommit block in the migration.

---

## 5. Abuse and performance

**The queue query**

```sql
SELECT i.id, i.order_id, o.order_number, i.product_id, i.product_name_snapshot,
       o.user_id, o.customer_email_snapshot, i.line_total_cents, i.currency, i.created_at
FROM order_items i JOIN orders o ON o.id = i.order_id
WHERE i.product_type = 'stl' AND i.fulfillment_status = 'awaiting_delivery'
  AND (:product_id IS NULL OR i.product_id = :product_id)
  AND (:user_id    IS NULL OR i.user_id    = :user_id)
  AND (i.created_at, i.id) > (:c_at, :c_id)            -- only when a cursor is given
ORDER BY i.created_at, i.id
LIMIT :limit + 1;
```

- **Oldest first:** `created_at` is the line's creation time, which equals the order's `placed_at` (both set in checkout Tx1). Ordering by placement is what `api-endpoints.md:560` says ("oldest first (`placed_at`)"). It is not payment time; see owner question 3.
- **Keyset with a reversible cursor:** opaque base64url of `{"c": "<aware ISO datetime>", "i": "<uuid>"}`. `decode_cursor` returns `(datetime, UUID)` or raises → 422 on `cursor`. "Reversible" means the cursor decodes losslessly to its key (no hash, no signature needed since it carries no authority), and the row-value comparison `(created_at, id) > (c, i)` resumes exactly. No offset pagination anywhere. Fetch `limit + 1` rows to decide `next_cursor`. A line that leaves the queue between pages is simply skipped; one that enters with an older `created_at` than the cursor (a retry-paid old order) does not appear in later pages, which is acceptable for a queue the administrator re-opens.
- **Index use:** the partial index `(created_at, id)` serves the ordered scan and the cursor range directly; the partial predicate matches the query's two constants. `product_id` / `user_id` are applied as filters on the index rows; the queue is small, so no second index (add one only if `EXPLAIN` on seeded data shows otherwise). The join to `orders` is by primary key for at most 100 rows. A test runs `EXPLAIN` and asserts the plan uses `ix_order_items_stl_awaiting` on a seeded set (§6), as `release_candidates_query` is EXPLAINed (`orders.py:251`).
- **Limits:** `limit` ≤ 100, default 25; `cursor` ≤ 200 chars; no free-text filter, no sort parameter, so there is no new injection surface.
- **Abuse of the POST:** per-administrator hourly rate limit (§2.2); body is a closed literal; one row-locked order per call; no loops. A compromised admin session cannot fabricate a delivery for a line that is not `awaiting_delivery`, because the state machine refuses it, and every success is audited with the actor.
- **Cost of the email:** one outbox row per delivery; no fan-out.

---

## 6. Tests (per category; `tests/<category>/…`)

**Unit (`tests/unit/ordering/`, `tests/unit/fulfillment/`)**
- [M] `stl_transition_refusal`: the full matrix `product_type × current status × target` — only `(stl, awaiting_delivery, delivered)` returns None; each other cell returns the documented refusal.
- [M] `derive_order_status` with the new helper: a single STL line `delivered` on a paid online order → `completed`; one STL `delivered` + one physical `pending` → `in_progress`; a `partially_refunded` order stays `partially_refunded` after delivery (the `refund_present` stop-gap).
- [M] `tests/unit/ordering/test_order_item_writers.py`: add `("ordering/infrastructure/orders.py", "set_line_delivered")` to `KNOWN_WRITERS` and `("ordering/public.py", "mark_stl_line_delivered")` to the caller set, and make the test fail if any other module writes `fulfilled_at` or `delivered_by`.
- [M] cursor round-trip: `decode(encode(x)) == x`; garbage, naive datetime and wrong shape → the 422 path.
- [N] architecture test: `fulfillment` imports only `*.public` of other contexts (covered by `test_deep_architecture.py` once the package has code).

**Integration (`tests/integration/fulfillment/`)** — real Postgres, `db_session`, the repository's seed helpers.
- [M] Queue lists only `awaiting_delivery` STL lines; a `pending` STL line, a `delivered` line, a `refunded` line, a `cancelled` line and a physical line in `awaiting_delivery`-adjacent states never appear.
- [M] Queue order is `(created_at, id)` ascending; two lines with equal `created_at` come out in `id` order; paging through 3 pages of 2 returns every line exactly once, and a mid-walk delivery does not duplicate or skip the others.
- [M] Queue fields: includes `customer_email` and `order_number`; **does not** include payment ids, provider references, contact phone, hashes or internal notes (assert on the exact key set).
- [M] Authorization on both routes: anonymous 401; customer 404 (never 403); admin without MFA 401 `MFA_REQUIRED`; POST without CSRF 403.
- [M] Mark delivered, happy path: 200; the row has `fulfilled_at` and `delivered_by` set together; `ck_order_items_stl_delivery_record` satisfied; one `order_status_history` row for the line with the admin as actor; one audit row; one `download` notification with `payload.event = "stl.delivered"` for the buyer (and none for anyone else); one outbox row to `customer_email_snapshot`, template `order_stl_delivered`.
- [M] Order status: only STL line delivered → order `completed`; STL delivered with a physical line `pending` → `in_progress`; the history gets an order-level row only when the status changes.
- [M] 409 `INVALID_STATE_TRANSITION` with the right `reason` for `delivered`, `refunded`, `cancelled`, `pending` and physical lines; **nothing written** in each case (row counts for history, audit, outbox, notifications unchanged).
- [M] 404 for an unknown order, an unknown item, and an item that belongs to another order; the three bodies are identical.
- [M] Rollback atomicity: force a failure in the outbox insert (monkeypatch) → the line is still `awaiting_delivery`, and no audit, history or notification row exists.
- [M] No external call inside the transaction: the test provider records zero `send` calls until `dispatch_outbox` runs; then exactly one.
- [M] A mark-sent on a line of a **partly refunded** order works and keeps the order `partially_refunded` (seeded via SQL; VS-030 supplies the real refund path).
- [M] Migration: `ix_order_items_stl_awaiting` exists, is partial on the exact predicate, columns `(created_at, id)`; `daily_download_cap` is absent from `settings`; downgrade restores it with value 20; `EXPLAIN` of the queue query uses the index on a seeded set.
- [N] Product and customer filters return the right subset and compose with the cursor.
- [N] `limit=0`, `limit=101`, malformed UUID filters → 422.
- [N] Rate limit: the N+1th POST in the window → 429.

**Concurrency (`tests/concurrency/`)**
- [M] Two administrators mark the same line at once (two sessions, a barrier before the call): exactly one 200 and one 409 `already_delivered`; exactly one audit row, one outbox row, one notification, one history row.
- [M] Mark-sent racing a direct SQL refund-style update that takes the `orders` lock and sets the line `refunded` (stand-in for VS-030): exactly one wins; if the refund wins, the POST is 409 `line_closed` and nothing else is written; if the POST wins, the line is `delivered` and the refund path sees it.
- [M] Mark-sent racing `mark_order_paid` on a still-`pending` line: the POST is either 409 `not_awaiting_delivery` or runs after payment and succeeds; never a delivered line on an unpaid order.
- [N] Ten administrators, one line: still exactly one winner.

**End-to-end (`tests/e2e/test_vs023b_stl_delivery.py`)**
- [M] register → verify → buy an STL online (mock provider, `scripts/mock_pay.py` path as in `tests/e2e/test_vs023_digital_purchase.py:122`) → the line appears in the queue → the administrator marks it sent → the customer sees `delivered` with `fulfilled_at` in order history and one new `download` notification, and `dispatch_outbox` sends one email.
- [M] The order's `status` is `completed` after delivery.

**Contract / snapshot**
- [M] `tests/unit/test_openapi_snapshot.py` compares against `docs/frontend-handoff/openapi.json` (`:9-14`): regenerate the snapshot in the same PR; the diff must show only the two new routes and their schemas.
- [M] `test_vs011_admin_boundary.py`'s route walk (`:389-395`) passes with the new routes (both under the admin router, both with CSRF on the unsafe one).
- [M] `test_settings_seed.py`, `test_admin_settings.py`, `test_deep_vs007_settings.py`, `test_public_settings.py`, `tests/concurrency/test_setting_update_race.py`: retarget every use of `daily_download_cap` (it is the working example in `test_admin_settings.py:129-292`, `:426-434` and `test_deep_vs007_settings.py:79`, `:320-331`) to another integer setting, and update the seeded-key count. Add [M] a test that `PATCH /admin/settings/daily_download_cap` is 404/422 as for any unknown key.

---

## 7. Docs and ADRs

### 7.1 Column-name corrections (`delivered_at` → `fulfilled_at`)

A grep of `docs/` for the word `delivered_at` finds **one** hit:
- `docs/frontend-handoff/BACKEND-RESPONSE.md:1801` — says `delivered_at` "(C8, provisional)". Correct it to `fulfilled_at` (and note that the same field is on every line type, ADR-033 d6).

Everything else already says `fulfilled_at`: `vertical-slice-plan.md:582`, `:662`; `docs/order-history.md:30`; ADR-033 d6; `database-design.md:1088`, `:1114`; `VS-023-digital-checkout-plan.md:1008`. The user's premise that the plan says `delivered_at` is therefore wrong for `vertical-slice-plan.md`; no change is needed there for naming. Also verify the generated OpenAPI for `OrderLine` uses `fulfilled_at` (it is built from the VS-025 schema).

### 7.2 Other doc updates in the implementing PR

- `docs/vertical-slice-plan.md`: VS-023b Status → In progress, then Done with an "As built" block; table row `:28` kept in sync (the two matched on 2026-10-21: both "Not started"); drop the `admin_users.py` clause at `:582` if the grep stays empty; note VS-029's `:744` ("created by VS-023b") remains true.
- `docs/requirments/api-endpoints.md:560-561`: confirm cursor/filter names; record the interim `OrderItemTransitionRead` response (or `AdminOrderDetail`, per owner question 2); `:1669` unchanged.
- `docs/frontend-handoff/BACKEND-RESPONSE.md:1159` ("will be deleted by VS-023b") → deleted; `:1119` settings sample drops the key; `:2325` queue entry gets the final shape. Regenerate `docs/frontend-handoff/openapi.json`.
- `docs/settings-registry.md:40` (row removed), `:137` ("seventeen seeded keys" → sixteen, recount the internal ones).
- New `docs/stl-delivery.md`: the contract (queue shape, transition errors and `reason` values, notification and email payloads, lock order), in the style of `docs/payment-recovery.md`.
- `docs/adr/README.md`: add the ADR-039 line. `SRS.md` §10.2 needs no change; SRS §23 has no new job.
- `database-design.md`: add the index to the `order_items` index list.

### 7.3 ADR-039 — Fulfillment owns the STL delivery workflow (proposed)

Decides: (1) Fulfillment owns the delivery use case, routes and notices; Ordering keeps all `order_items` SQL and the writers allow-list (ADR-032 d6 said "Fulfillment owns nothing yet"; this is the first thing it owns); (2) `409 INVALID_STATE_TRANSITION` carries a `reason` for each refusal, as ADR-036 does for manual release; (3) queue ordering is `(created_at, id)` with an opaque keyset cursor; (4) a delivery is an outbox email plus an in-app notification, sent after commit; (5) the `refund_present` stop-gap until VS-030; (6) the transition table is a pure function that VS-029 extends. Number re-checked against `origin/main` before writing (expected 039).

---

## 8. Implementation steps, in order, with checkpoints

Branch `vs-023b-stl-delivery`, one PR. Run the full suite at each checkpoint (the user said not to run tests while planning; this applies to implementation).

1. **Pre-flight and head.** Fetch, branch from `main`, re-derive the alembic head (expect `fcd589e89e59`) and the highest ADR (expect 038).
2. **Domain table.** `line_transitions.py` + unit tests.
3. **Entity + store.** Add `fulfilled_at` / `delivered_by` to `OrderLine` and `_LINE_COLUMNS`; `set_line_delivered`; `stl_delivery_page`; update the `lock_lines` comment. Update the writers allow-list test in the same commit (it will fail otherwise).
4. **`ordering.public`.** `mark_stl_line_delivered`, `status_inputs_for`, `stl_delivery_page`, `__all__`. Unit tests for status derivation.
5. **Migration + model index.** Index, `daily_download_cap` delete, registry entry removed, flipped schema test, settings tests retargeted.
   **CHECKPOINT 1 (schema and ordering core):** migration upgrades and downgrades on a clean DB and on a DB with `awaiting_delivery` rows; `alembic heads` shows one head; writers test, schema tests, settings tests and the full unit suite are green. Review point: the `status_inputs_for` stop-gap and the migration downgrade seed.
6. **Fulfillment use case + notices.** `mark_stl_delivered`, `SqlStlNotices`, audit action name.
7. **API.** The two routers, cursor codec, schemas, rate limit, mount in `admin.py`; regenerate `openapi.json`.
8. **Tests.** Integration, then concurrency, then e2e (§6).
   **CHECKPOINT 2 (behaviour):** every [M] test green, the boundary route walk and the OpenAPI snapshot green, EXPLAIN test green, mypy/ruff clean. Review point: the two-administrator race and the refund-stand-in race.
9. **Cleanup.** Delete `digital_assets` (+ test folders, `CONTEXTS` entry), the `partitions.py:12` sentence; re-run the architecture tests.
10. **Docs and ADR-039.** §7; vertical-slice-plan status and "As built".
11. **PR.** One PR to `main`; description lists the migration id, the new routes, and the owner decisions applied.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Refund inputs absent in `derive_order_status` flip a `partially_refunded` order to `completed` on delivery | The `status_inputs_for` stop-gap plus a [M] test; VS-030 replaces the helper (§3.3) |
| A new `order_items` writer bypasses the lock discipline | Writers allow-list test updated in the same PR; the new writer runs only under `lock_order_for_change` |
| Response contract churn when VS-029 returns `AdminOrderDetail` | Interim `OrderItemTransitionRead` is explicit and documented as provisional (owner question 2) |
| OpenAPI snapshot drift blocks CI | Regenerate in the same commit as the routes |
| Removing `daily_download_cap` breaks five test files that use it as their example | Retarget first (step 5), before deleting the registry entry |
| The outbox is at-least-once (`outbox.py:23-30`), so a customer could get the "sent" email twice if a commit fails after a successful send | Accepted and inherent; the in-app notification is exactly-once. Noted in `docs/stl-delivery.md` |
| The administrator marks sent but the real email never left their mailbox | Out of the platform's control (ADR-019); the audit row records who and when |
| The queue's oldest-first by placement time can bury a retry-paid old order at the front | Intentional (it is the oldest debt); owner question 3 |
| Unpaid-order edge: a `pending` STL line is refused; if payment verification and POST race, one waits on the lock | Covered by the concurrency test |
| Deleting an administrator account while `delivered_by` references it | FK is `RESTRICT` (`models.py:254`); anonymisation (ADR-009) keeps the user row, so the record survives |

---

## 10. Owner questions (each with a recommendation)

1. **Where does the delivery code live?** `fulfillment` (ADR-019 d8) with Ordering keeping the SQL, or everything in `ordering`? *Recommend:* `fulfillment` owns routes and use case; Ordering keeps writers (ADR-039). It matches ADR-019 d8 and keeps one writers registry.
2. **What does the transition route return today?** `api-endpoints.md:561` says `AdminOrderDetail`, which VS-029 builds. *Recommend:* return the small `OrderItemTransitionRead` now and let VS-029 switch to `AdminOrderDetail` before any frontend depends on it; mark it provisional in the handoff doc. The alternative is to block 023b on VS-029, which reverses the dependency order.
3. **Oldest first by what?** Order placement (`created_at`, matches `api-endpoints.md:560`) or payment verification time (needs a new column or `updated_at`, which is not a stable paid time)? *Recommend:* placement time, no new column.
4. **Customer identity in the queue.** `orders` has no customer name; the queue shows `customer_id` and `customer_email_snapshot`. Is that enough, or must it show the account's display name (a cross-context read from Identity)? *Recommend:* email only; the email is what the administrator needs to send to.
5. **Refund-stop-gap.** Accept the `refund_present`-from-current-status stop-gap until VS-030, or require VS-030's refund query first? *Recommend:* accept the stop-gap; it is one function and VS-030 owns the replacement.
6. **Rate limit for mark-sent.** Per-administrator hourly cap? *Recommend:* 300 per hour (well above a human pace, below a script), a constant in a `fulfillment` limits module, like `payments.domain.limits`.
7. **Email copy.** Is "your STL file has been sent, check your inbox and spam" (SRS §10.2 step 5) the final wording, and does the template name `order_stl_delivered` suit? *Recommend:* yes; wording is a frontend/email-template concern and not blocking.
8. **Stale-delivery reminder.** Should the platform flag lines unsent for more than N days (the SRS §30.2 delivery-time promise is still open)? *Recommend:* out of V1; show `queued_at` and let the administrator sort by eye; revisit when the delivery-time promise is decided.
9. **Remove `daily_download_cap` now, in this PR's migration?** *Recommend:* yes, as the plan says (`vertical-slice-plan.md:578`); the downgrade re-seeds it, so it is reversible.
10. **One PR or two?** *Recommend:* one PR with two checkpoints (§8); the migration is one index and one row delete, so a separate schema PR (the VS-024 pattern) adds review overhead without reducing risk.
