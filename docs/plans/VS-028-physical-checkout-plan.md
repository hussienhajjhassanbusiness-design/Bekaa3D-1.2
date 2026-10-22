# VS-028 — Physical Checkout: Delivery, Pickup, Payment Method, Dispatch Estimate: Implementation Plan

**Status:** DONE (2026-10-22). PR A (schema, settings, salt) on branch `vs-028-schema`, merged;
PR B done (branch `vs-028-checkout`, which replaces the name `vs-028-physical-checkout` used below; 2026-10-22; deviations in ADR-038). Owner decisions: Q1–Q16 as recommended; Q17 decided (Revision 2).
**Date:** 2026-10-20
**Planned against alembic head:** `8d2f6a1c3e57` (`offers_remind_at`, VS-040).
- Derived statically from `revision` / `down_revision` in `migrations/versions/`: 24
  files, one linear chain, one head. No file names `8d2f6a1c3e57` as its `down_revision`.
  No merge revisions.
- This slice's migration (PR A, §4) was planned with `down_revision = "8d2f6a1c3e57"`; after merging VS-041 it is re-parented onto `d5507ee63176` (`order_items_offer_once`), the single head.
- Re-derive the head immediately before `alembic revision`: VS-023b also plans a
  migration (`docs/vertical-slice-plan.md:575-578`).

**Pre-flight (2026-10-20):** `git fetch`, `git checkout main`, `git pull --ff-only`
(already up to date at `bf0abd1`). Remote branches: `feat/vs-038-wishlist`,
`fix/vs-040-accept-expected-amount`, `vs-022-mixed-cart`, `vs-023-checkout`,
`vs-023-schema`, `vs-024-recovery`, `vs-024-schema`, `vs-025-order-history`,
`vs-039-offer-submission`, `vs-040-offer-negotiation`, `vs-046-security-retention`. None
names VS-028, physical, cash, shipping or a new checkout, and no ref holds a
`VS-028` file or an ADR above 036. Highest ADR on `origin/main`: **ADR-036**, so this
slice's ADR is **ADR-038** (re-check before writing it).

**Format:** follows [`VS-024-payment-recovery-plan.md`](VS-024-payment-recovery-plan.md).
Every `file:line` below is on `main` at `bf0abd1`.

**Name corrections against the request:** the existing guards are `require_digital_only`
and `require_online` (`src/app/ordering/domain/checkout_rules.py:83`, `:91`); there is no
`require_physical_only`. There is no `lock_address_for_share` yet: the address store has
`lock_address_book` (users row) and an unlocked `get_live`
(`src/app/identity/application/ports.py:162-181`,
`src/app/identity/infrastructure/addresses.py:71-89`). This plan adds the share-locked read
(§3.3).

---

## Revision 3 (2026-10-20): PR A as built

- **Two `RESTRICT` foreign keys to `users`**, as database-design §14 lists them:
  `cash_payment_blocks.user_id` (`database-design.md:1953`, `fk_cash_payment_blocks_user`)
  and `cash_payment_blocks.cleared_by` (`database-design.md:1955`,
  `fk_cash_payment_blocks_cleared_by`). Both join `RESTRICT_TO_USERS_ALLOWED` in
  `tests/integration/test_deep_db_constraints_and_migrations.py` (owner-approved; ADR-032
  Consequences). The purge of never-verified accounts cannot reach them: a block needs a
  cash order from a verified customer, and `cleared_by` is an administrator. A test asserts
  that deleting such a user is refused (`23503`, each FK by name). Recorded in
  [ADR-038](../adr/ADR-038-physical-checkout-and-cash-eligibility.md) d3; the plan missed
  this guard.
- **ADR-038 is created in PR A** with the schema decisions (owner request); PR B adds the
  checkout decisions (§7).
- **Seeds fixed (owner-approved):** two existing tests seeded `contact_phone_hash` values
  that `ck_orders_phone_hash_format` now refuses (`"HASH-SENTINEL"`, `"hash"`); they now
  seed valid 64-hex values with every assertion unchanged.
- **Deviations from the §8 PR A file list:** `tests/conftest.py` (a test-only
  `PHONE_HASH_SALT` default, like its `CAPTCHA_PROVIDER` line);
  `tests/integration/test_model_migration_parity.py` (the new table);
  `tests/integration/test_deep_db_constraints_and_migrations.py` (the allowlist);
  `tests/integration/ordering/test_order_history_api.py` and
  `tests/integration/negotiation/test_offer_schema.py` (the seeds); `docs/adr/ADR-038-…`
  and `docs/adr/README.md`. Migration id `fcd589e89e59`.

## Revision 2 (2026-10-20): owner decisions before PR A

- **Q1–Q16:** as recommended (§10).
- **Q17:** the `contact_phone` scan (§6.5) allowlists **exact routes only**: the owner's
  order detail `GET /api/v1/me/orders/{order_id}` (`contact_phone`), the address book
  `GET/POST /api/v1/me/addresses`, `GET/PATCH /api/v1/me/addresses/{address_id}` (`phone`),
  and later VS-029's admin order detail `GET /api/v1/admin/orders/{order_id}`. The
  **phone hash is never allowlisted** anywhere outside the `orders` and
  `cash_payment_blocks` columns.

## Revision 1 (2026-10-20): owner answers and review items

These are recorded as decided. They bind PR A and PR B.

**Q1–Q16 are answered as recommended in §10**, with one addition:

- **Q13:** a mixed cart whose STL is dropped as already owned may pay cash. The dropped
  STL is **still named** in `dropped_lines` (`checkout_schemas.py:101-104`), on the cash
  path as on the online path. That includes the stored replay body. Test in §6.2.

**Review items:**

1. **Lock order.** §8.1 now quotes ADR-024 d9 and ADR-036 d14 beside this plan's order,
   and confirms that no path takes the phone lock before the cart or address lock.
   - The checkout-versus-block-insert race is a real-Postgres [M] test (§6.3 R3).
   - A static [M] test pins the call order (§6.1).
2. **Phone and hash never leak.**
   - The **hash** appears in no API response, log, audit row, outbox or notification
     payload, or error body; it lives only in `orders.contact_phone_hash` and
     `cash_payment_blocks`.
   - The **phone number** appears in no log, audit row, outbox or notification payload,
     or error body, and in **no VS-028 response**: `CheckoutRead` no longer carries the
     contact-phone snapshot (§2.1).
   - Two existing responses already return it to its owner:
     - `OrderDetailRead.contact_phone` (VS-025, `ordering/api/order_schemas.py:149`,
       `:177`);
     - the address book's own `phone` (`api-endpoints.md:793-810`).
     VS-029's admin order detail is also planned to return it (`api-endpoints.md:558`).
     These are recorded as **Q17** for the owner and are allowlisted, by route, in the
     scan.
   - A [M] scan test covers every surface (§6.5).
   - A log pattern redacts E.164 numbers inside strings (§3.6), because a CHECK violation
     carries its parameters into the error text.
3. **`free_shipping_threshold` removal (Q11).**
   - `docs/frontend-handoff/BACKEND-RESPONSE.md` gets a dated entry: "2026-10-20 (VS-028
     PR A): `free_shipping_threshold` removed from `GET /settings/public`;
     `cash_payment_enabled` and `cash_max_order_total` added" (§7).
   - The public-settings test asserts that the field is absent, not just ignored (§6.2).
4. **Indistinguishable cash refusals.** A [M] test asserts that a refusal matched by
   account and one matched by phone return byte-identical bodies, for both
   `cash_blocked` and `open_orders`. Both requests send the same `X-Request-ID`, so
   `request_id` is equal (`api/middleware.py:27-31`, `api/errors.py:44-54`). §6.2.
5. **Boot test** for the `PHONE_HASH_SALT` refusal (short and placeholder) outside
   development/test, through `app.main.lifespan` and `app.worker.on_startup` like
   `tests/integration/payments/test_payment_startup.py`. Now [M] (§6.1, §6.2).
6. **Cuttable tests:** every [N] test is listed in §6.8. PR A's exact file list is in §8.

---

## 0. Decisions this plan takes (summary)

| # | Decision | Where |
|---|---|---|
| D1 | One migration (PR A): `cash_payment_blocks`, three cash settings seeded, `free_shipping_threshold` deleted, two format CHECKs and one partial index on `orders`. Reversible; one head. | §4 |
| D2 | PR A merges first (migration lock, `CONTRIBUTING.md:42-47`). Because deleting the settings row breaks `GET /settings/public` for code that still lists it, PR A also carries the registry, `PublicSettingsRead`, the `PHONE_HASH_SALT` setting and their tests. No checkout code. | §4.1, §8 |
| D3 | `ONLINE_PAYMENT_UNAVAILABLE` (503) is raised only for `payment_method = online`. A cash checkout works with `PAYMENT_PROVIDER=none`. ADR-038 amends ADR-032 d12 to say so. | §2.1, §3.4 |
| D4 | A cash checkout is **one** transaction: claim, place, complete the claim, COMMIT. No payment row, no provider call, no Tx2. | §2.1 |
| D5 | Lock order on the cash path: `idempotency_records → carts → addresses (FOR SHARE, delivery only) → phone advisory lock`, then reads and INSERTs only. No existing `orders` row is locked. | §8.1 |
| D6 | The phone lock is `pg_advisory_xact_lock(CASH_PHONE_LOCK_NS, hashtext(phone_hash))`, the two-int form. Its key space does not overlap the one-bigint locks already in use. VS-031's block insert takes the same lock through the same function. | §3.5, §8.1 |
| D7 | Phone hash: `HMAC-SHA256(key = PHONE_HASH_SALT, msg = E.164)`, lowercase hex, computed in `app.core.security.hash_phone`. The salt is a required `SecretStr`, never rotated, and redacted from logs. | §3.6 |
| D8 | Open cash orders = `payment_method = 'cash' AND status = 'in_progress'`, matched by `user_id` **or** `contact_phone_hash`. It is equivalent to `payment_due` because a paid cash order can never derive `in_progress` (§3.1, proved by a unit test). | §3.1, §3.5 |
| D9 | The §7.4 matrix is one pure function over the **kept** lines (after owned STLs are dropped). | §3.1 |
| D10 | Contact phones are normalised in `CheckoutRequest`. The idempotency hash therefore covers the normalised number, so two spellings of one phone are one body. | §2.1, §3.7 |
| D11 | Dispatch: `estimated_dispatch_at = placed_at + max(lead × ceil(qty ÷ batch))` calendar days over physical lines. None for an STL-only order. Lead time and batch size are snapshotted on each physical line. | §3.1 |
| D12 | `amount_due_cents` (ADR-033 owner decision) is one pure function, `amount_due_cents(lines)`, published for VS-029's handover. | §3.1, §3.8 |
| D13 | Snapshots are immutable by construction: no `UPDATE orders` writes a snapshot column, enforced by a static writer test like `test_order_item_writers.py`. No database trigger (Q9). | §6.1 |

## 1. Scope and non-goals

### In scope (VS-028 only)

- `POST /api/v1/checkout` for every §7.4 row (`docs/SRS.md:668-678`):
  - delivery and pickup;
  - online for every cart type;
  - cash for physical-only carts (`docs/vertical-slice-plan.md:693-735`).
- Address snapshot, contact-phone snapshot, its keyed hash, lead time and batch size
  snapshots, and `estimated_dispatch_at` (SRS §7.3 steps 7, 10, 11, 13, `SRS.md:658-664`;
  §8.6 `:718-722`).
- Cash eligibility and limits under the cart lock and the phone lock (SRS §9.8.1,
  `SRS.md:792`; BR-141, BR-145).
- The `cash_payment_blocks` table, and a store VS-029 and VS-031 extend.
- Settings:
  - seed `cash_payment_enabled`, `cash_max_open_orders`, `cash_max_order_total`;
  - delete `free_shipping_threshold` from the table, the registry and the public
    allowlist (ADR-024 Consequences `:71`).
- `PHONE_HASH_SALT`: config, `.env.example`, test placeholders, redaction, CONTRIBUTING.
- Emails and responses:
  - the cash placement email and notification;
  - "delivery fee paid to the courier on delivery" on delivery responses and emails;
  - fulfillment and dispatch in the online confirmation email.
- `amount_due_cents` on `OrderSummaryRead`, `OrderDetailRead` and the cash `CheckoutRead`
  (`docs/vertical-slice-plan.md:735`).

### Non-goals, and exactly who owns them

| Not here | Owner | Why |
|---|---|---|
| Admin order queue, physical transitions, BR-148 gate, cash handover, cash-block list/search/clear, the cash-due index | **VS-029** (`vertical-slice-plan.md:737-781`) | VS-028 creates cash orders and the block table; VS-029 moves and pays them. |
| Inserting blocks; customer and admin cancel; `cancel_reason` writes | **VS-031** (`:844-899`) | VS-028 publishes the phone lock and `insert_block` for it (§3.8). |
| Refunds, cash refund caps | VS-030 | No `refunds` table yet. |
| Real providers and the provider list setting | VS-032 | `choose_provider` already takes a set (`checkout_rules.py:162-176`). |
| Offer checkout | VS-041 | It will call `place_order` with `source = offer`. VS-028 keeps the signature extensible but adds no offer code. |
| STL delivery queue | VS-023b | Unchanged; a mixed order's STL line enters it through the existing `mark_order_paid` (`ordering/public.py:105-115`). |
| `daily_download_cap` deletion | VS-023b | Same pattern as this slice's deletion. |

---

## 2. API and jobs

### 2.1 `POST /api/v1/checkout` (changed)

**Request** (`CheckoutRequest`, `src/app/ordering/api/checkout_schemas.py:35-67`): the
fields already exist. VS-028 gives them meaning and validation.

| Field | Rule |
|---|---|
| `payment_method` | `online` \| `cash` |
| `payment_provider` | online only. With `cash` → 422 `PAYMENT_METHOD_NOT_ALLOWED` (`provider_not_applicable`, Q2) |
| `fulfillment_method` | required when any kept line is physical; must be absent for STL-only |
| `address_id` | delivery only; required there |
| `contact_phone` | pickup only; required there. A field validator normalises it with `normalise_lebanese_phone`; an invalid number → 422 `VALIDATION_ERROR` at `body.contact_phone`. Sent with delivery → 422 `INVALID_FULFILLMENT` (Q1) |
| `accept_cash_terms` | `true` required for cash, otherwise 422 `VALIDATION_ERROR` at `body.accept_cash_terms`; ignored for online (as today, `:46-48`) |
| `customer_note` | unchanged |

`CheckoutRequest.command()` (`:55-67`) stops collapsing the fulfillment fields into
`fulfillment_requested`. `CheckoutCommand` (`checkout_rules.py:40-50`) carries
`fulfillment_method`, `address_id`, `contact_phone` (E.164 or None) and `accept_cash_terms`.

**Responses**

- `201 CheckoutRead`:
  - online: unchanged shape;
  - cash: `payment: null`.
- `order` gains:
  - `estimated_dispatch_at`;
  - `delivery_fee_note` (the fixed string for delivery orders, else null);
  - the address snapshot (recipient, governorate, city, area, street, landmark notes).
    **Not the contact phone and never its hash** (Revision 1 item 2);
  - `payment_due`;
  - `amount_due_cents`.
- `dropped_lines` is filled on both paths (Q13).
- `CheckoutRead.payment` becomes `CheckoutPaymentRead | None` (`:109`). This is an
  additive contract change; `api-endpoints.md:1283-1293` and `openapi.json` are updated.

**New and changed refusals** (all roll the claim back, like every refusal today,
`checkout.py:1-3`):

| Code | When |
|---|---|
| 422 `INVALID_FULFILLMENT` | §7.4 mismatch; a deleted, foreign or unknown `address_id` (same answer for all three, ADR-027 d7 `:25`); pickup while `pickup_address` is null (Q16) |
| 422 `PAYMENT_METHOD_NOT_ALLOWED` | `reason`: `cash_requires_physical` (existing, `checkout_rules.py:94`), `cash_disabled`, `zero_total` (existing, `checkout.py` service `:98-99`), `cash_blocked`, `provider_not_configured` / `provider_required` (existing), `provider_not_applicable` |
| 422 `CASH_PAYMENT_LIMIT_REACHED` | `reason`: `open_orders` or `order_total` (`api-endpoints.md:203`) |
| 503 `ONLINE_PAYMENT_UNAVAILABLE` | **online only** now (D3) |

**Flow** (`src/app/ordering/api/checkout.py:260-334`):

- **Online:** unchanged. Tx1 claims and places the order (`:273-303`), the provider is
  called with no transaction open (`:305-308`), and Tx2 stores the reference
  (`:325-333`).
- **Cash:** inside Tx1, after `place_order` returns `payment is None`:
  - `claims.attach(...)`;
  - then `claims.complete(record_id, 201, body)`;
  - COMMIT and return 201.

  No `start_online_payment`, no Tx2, and so no `in_progress` claim window and no crash
  window (D4).
- **Idempotency:** `request_hash(SCOPE, body.model_dump(mode="json"))` (`checkout.py:271`)
  already covers `payment_method`. The same key with only `payment_method` changed is a
  `Conflict` → 409 `IDEMPOTENCY_KEY_CONFLICT` (`:287-288`). No code change, only a test.
  A cash replay returns the stored 201 with `Idempotent-Replayed: true` (`:283-284`).

### 2.2 `GET /api/v1/settings/public` (changed)

`free_shipping_threshold` leaves; `cash_payment_enabled` and `cash_max_order_total` join
(`docs/settings-registry.md:134-142`). `PublicSettingsRead`
(`src/app/platform/api/schemas.py:124-143`) and the route's docstring ("five",
`settings.py:263-275`) change together.

### 2.3 `GET /api/v1/me/orders`, `GET /api/v1/me/orders/{id}` (changed)

`amount_due_cents: int | None` on `OrderSummaryRead` (`order_schemas.py:29-50`) and
`OrderDetailRead` (`:136-180`). It is in the order's currency (`total.currency`) and null
unless `payment_due`. `OrderDetailRead` also gains `delivery_fee_note`
(`api-endpoints.md` OrderDetail list).

### 2.4 Jobs

None new. The existing jobs are shown not to select cash orders (§5, §6.2).

---

## 3. Layers, function by function

### 3.0 Package ownership (unchanged from ADR-032 d6, `:31`)

- **Ordering** owns:
  - checkout and the matrix;
  - cash rules and `cash_payment_blocks`;
  - the phone lock and dispatch.
- **Identity** publishes a share-locked address read.
- **Catalog** publishes lead time and batch size on `CartProduct`.
- **Platform** owns settings.
- **`app.core`** (shared kernel) owns phone normalisation (`core/phone.py:22-33`) and the
  phone hash.
- **Payments** is touched only for the confirmation email payload.
- Cross-context calls go through `public` / `application.ports` only
  (`tests/unit/test_deep_architecture.py:72-118`).

### 3.1 Pure rules (`app.ordering.domain`, no I/O)

New module `app/ordering/domain/fulfillment.py`:

```text
resolve_fulfillment(lines, command) -> Fulfillment
  # SRS 7.4 over the kept lines. Fulfillment(method, address_id, contact_phone) or
  # raises InvalidFulfillmentError / PaymentMethodNotAllowedError("cash_requires_physical").
```

| Kept lines | method | address_id | contact_phone | cash |
|---|---|---|---|---|
| STL only | must be None | must be None | must be None | `cash_requires_physical` |
| physical, delivery | `delivery` | required | must be None (Q1) | allowed |
| physical, pickup | `pickup` | must be None | required | allowed |
| mixed, delivery | `delivery` | required | must be None | `cash_requires_physical` |
| mixed, pickup | `pickup` | must be None | required | `cash_requires_physical` |

```text
dispatch_days(lines: Sequence[NewOrderLine]) -> int | None
  # BR-037 / SRS 8.6: max over physical lines of lead * ceil(qty / batch); None if none.
estimated_dispatch_at(placed_at, days) -> datetime | None   # placed_at + timedelta(days)
```

New module `app/ordering/domain/cash.py`:

```text
CASH_PHONE_LOCK_NS: Final = 0x43415348   # "CASH"; int4 namespace of the two-int lock
cash_precheck(lines, total_cents, enabled) -> None
  # Before the phone lock: all physical, enabled, total > 0, else PAYMENT_METHOD_NOT_ALLOWED.
cash_limits(*, blocked, open_orders, max_open, total_cents, max_total) -> None
  # Under the lock: blocked -> PAYMENT_METHOD_NOT_ALLOWED("cash_blocked");
  # open_orders >= max_open -> CASH_PAYMENT_LIMIT_REACHED("open_orders");
  # total_cents > max_total -> CASH_PAYMENT_LIMIT_REACHED("order_total").
amount_due_cents(lines) -> int   # sum of line_total_cents over non-cancelled lines
```

- `NewOrderLine` (`orders.py:17-28`) gains `lead_time_days_snapshot: int | None` and
  `batch_size_snapshot: int | None`. `price_lines` (`checkout_rules.py:128-147`) fills them
  from `CartProduct` for physical lines and leaves None for STL. This matches
  `ck_order_items_*` at `ordering/infrastructure/models.py:297-302`.
- `NewOrder` (`orders.py:31-47`) gains:
  - `fulfillment_method`;
  - the address snapshot (`recipient_name`, `governorate`, `city`, `area`, `street`,
    `landmark_notes`);
  - `contact_phone_snapshot`, `contact_phone_hash`;
  - `estimated_dispatch_at`, `cash_terms_accepted_at`.

  `insert_order` writes `vars(order)` already (`infrastructure/orders.py:79-95`), so no
  store change is needed.
- `Order` (`orders.py:50-65`) gains `estimated_dispatch_at`, for the payment email (§3.9).
- `require_digital_only` and `require_online` are deleted; their tests
  (`tests/unit/ordering/test_checkout_rules.py:103`) move to `resolve_fulfillment`.
- **D8 invariant:** `derive_order_status` (`order_status.py:35-53`) returns
  `IN_PROGRESS` for a paid order only when some line is non-terminal. The cash handover
  (VS-029, `vertical-slice-plan.md:745-748`) requires every live line to be `shipped` /
  `ready_for_pickup` and makes them all `delivered` / `picked_up`. No edge leaves those
  states (none in SRS or the plan). So a paid cash order is `completed`, `refunded` or
  `partially_refunded`, and `status = 'in_progress'` on a cash order means unpaid and
  uncancelled.
  - A unit test pins this over every terminal line combination.
  - ADR-038 records that a future edge out of `delivered` / `picked_up` must revisit the
    count.

### 3.2 Catalog (`app.catalog`)

- `CartProduct` (`catalog/domain/storefront.py:164-177`) gains
  `production_lead_time_days: int | None = None` and `batch_size: int | None = None`.
  They default to None, so every existing constructor still works.
- `SqlCartProductReader.get_many` (`catalog/infrastructure/cart_product_reader.py:32-64`)
  selects both columns. The product CHECK guarantees them for physical products
  (`catalog/infrastructure/models.py:161`).

### 3.3 Identity (`app.identity.public`)

```text
@dataclass(frozen=True) CheckoutAddress: recipient_name, phone, governorate, city,
  area, street, landmark_notes
async def lock_checkout_address(session, *, address_id, user_id) -> CheckoutAddress | None
  # SELECT ... FROM addresses WHERE id AND user_id AND deleted_at IS NULL FOR SHARE.
  # None for unknown, foreign or deleted alike (ADR-027 d7).
```

- The lock is implemented in `SqlAddressStore` as `get_live_for_share`, beside `get_live`
  (`identity/infrastructure/addresses.py:85-89`).
- Ordering reads it through a new port, `CheckoutAddresses`, in
  `ordering/application/ports.py`. The route wires it (the `payment_attempts` pattern,
  `checkout.py:294`).
- Address writers take `users FOR NO KEY UPDATE` first (`addresses.py:71-74`), then
  `UPDATE addresses`. The `UPDATE` waits for checkout's `FOR SHARE`; the users lock does
  not conflict with checkout's `FOR KEY SHARE` from the `orders.user_id` foreign key.
- So an edit or delete racing a checkout either lands before (checkout sees the new row,
  or None → 422) or after (the order holds the old snapshot). §6.3 tests both.

### 3.4 `place_order` (`ordering/application/services/checkout.py:59-151`, changed)

New parameters:

- `addresses: CheckoutAddresses`;
- `cash: CashChecks` (port, §3.5);
- `notices: OrderNotices` (port, §3.9);
- `hash_phone: Callable[[str], str]`.

`PlacedOrder.payment` becomes `PaymentAttemptRef | None` (`:51-56`).

Sequence (SRS §7.3 numbering, `SRS.md:652-664`):

1. `accepting_orders` (`:74-75`), unchanged.
2. **D3:** `configured = attempts.configured_providers()`. If
   `command.payment_method is ONLINE and not configured`, raise
   `OnlinePaymentUnavailableError` (`:76-78` today raises for every request). It keeps its
   place before the cart lock, so an online request's error precedence is unchanged.
3. Lock the cart (`:79-81`); revalidate lines (`:82-83`); split owned STLs (`:86-91`).
4. `resolve_fulfillment(kept, command)`: SRS step 7 (replaces `:84-85`).
5. Delivery: `addresses.lock_for_share(address_id, user_id)`; None → 
   `InvalidFulfillmentError`. Pickup: the phone is `command.contact_phone`.
6. Delivery: `phone = normalise_lebanese_phone(address.phone)`, re-normalised so that a
   hand-edited row still hashes the canonical form. Then `phone_hash = hash_phone(phone)`
   for every physical order, online or cash.
7. Price changes (`:92-93`), consent (`:94-95`) and **cash terms**
   (`ConsentRequiredError` with field `accept_cash_terms`).
8. `price_lines` / `totals` (`:96-97`): SRS step 8.
9. Payment method (SRS step 9):
   - **online:**
     - `total == 0` → `zero_total` (`:98-99`);
     - `choose_provider` (`:100`);
   - **cash:**
     - a `payment_provider` was sent → `provider_not_applicable`;
     - `cash_precheck(kept, total, settings.get_bool("cash_payment_enabled"))`;
     - `await cash.lock_phone(phone_hash)`;
     - `cash_limits(blocked = await cash.active_block(user_id, phone_hash),
       open_orders = await cash.open_order_count(user_id, phone_hash),
       max_open = settings.get_int("cash_max_open_orders"),
       max_total = settings.get_money_cents("cash_max_order_total"), ...)`.
10. `status = derive_order_status(OrderStatusInputs(method, False, False, lines=(PENDING,)*n))`:
    `PENDING_PAYMENT` online, `IN_PROGRESS` cash (`order_status.py:39-42`).
11. Insert order and lines (`:107-127`), all lines `PENDING`. Online: `open_attempt`
    (`:128-134`). Cash: none.
12. History (`:135-137`). Audit `order.placed` (`:138-149`): `payment_method`,
    `fulfillment_method`, `payment_id` or null. **Never the phone or its hash.**
13. Cash: `notices.cash_order_placed(order, lines)`.
14. Clear the cart (`:150`).

`SettingsSource` (`ports.py:109-112`) gains `get_int` (it exists on `SettingsReader`,
`settings_reader.py:76-83`) and `get_money_cents`, which is new on `SettingsReader`: the
`amount_cents` of a validated money value.

### 3.5 Ordering infrastructure

`SqlCashChecks` (new, `ordering/infrastructure/cash.py`), implementing port `CashChecks`:

```text
async def lock_phone(self, phone_hash: str) -> None
  # SELECT pg_advisory_xact_lock(:ns, hashtext(:h)); released at COMMIT/ROLLBACK.
async def active_block(self, user_id, phone_hash) -> bool
  # EXISTS uncleared block WHERE user_id = :u OR contact_phone_hash = :h
  # (two partial indexes, database-design.md:2276-2277; written as UNION ALL of two EXISTS).
async def open_order_count(self, user_id, phone_hash) -> int
  # count(*) FROM orders WHERE payment_method='cash' AND status='in_progress'
  #   AND (user_id = :u OR contact_phone_hash = :h)   (D8; UNION of ids, so one order counts once)
```

- **Two-int key space:** the two-int form of `pg_advisory_xact_lock` and the one-bigint
  form used today (`payments/infrastructure/alerts.py:46-47`,
  `identity/infrastructure/repositories.py:271`, `jobs/partitions.py:87`,
  `platform/infrastructure/repositories.py:229`) are separate key spaces in PostgreSQL. So
  no phone lock can collide with an alert or job lock.
- **`hashtext` collisions:** two phones that collide only serialise two unrelated
  checkouts, which is harmless.
- **Read Committed:** the default; there is no `isolation_level` anywhere in `src/`. The
  block and count reads run after `lock_phone` returns, so each sees every transaction
  that held the lock before and committed (§8.1, race R1).

`SqlCashBlockStore` (new, same module) is the interface VS-029 and VS-031 extend (§3.8):

```text
async def insert_block(self, *, user_id, phone_hash, order_id, reason, at) -> bool
  # INSERT ... ON CONFLICT (order_id) DO NOTHING; caller holds the phone lock (VS-031).
```

VS-028 calls `insert_block` only from tests (seeded blocks). `CashPaymentBlockModel` is added
to `ordering/infrastructure/models.py`.

### 3.6 `app.core`: phone hash and config

- `core/config.py`: `phone_hash_salt: SecretStr`, required with no default, beside
  `ip_hash_salt` (`:26-29`). A comment says it is never rotated.
- `core/security.py`:

  ```text
  def hash_phone(e164: str) -> str
    # HMAC-SHA256(key=PHONE_HASH_SALT bytes, msg=e164 bytes).hexdigest(); ADR-024 d6.
    # Refuses a non-E.164 input (ValueError), so no caller can hash a raw spelling.
  ```

  The key is read from `get_settings()` each call, like the IP pepper (`security.py:55`).
  The env value is cached by `lru_cache`, so a change needs a restart.
- **Boot check (Q5):** a new `check_phone_hash_salt(settings)` in `core/security.py`
  raises `ConfigurationError` when the salt is shorter than 32 characters or starts with
  `generate_with__`. It runs in every environment except `development` and `test`.
  - It is called beside `configured_payment_providers(settings)` in `main.py:31`
    (`lifespan`) and `worker.py:42` (`on_startup`), so the API and the worker refuse
    alike.
  - The error names the setting, never its value.
- **Redaction:** `core/logging.py:_SENSITIVE_KEYS` (`:15-48`) gains `phone_hash_salt`,
  `contact_phone`, `contact_phone_snapshot`, `contact_phone_hash` and `phone`. A 64-hex
  hash inside a string is already redacted (`:73`).
  - `_PATTERNS` gains one linear-time pattern for a Lebanese number inside a string,
    `(?<![0-9+])\+?961[0-9]{7,8}(?![0-9])` → `[redacted-phone]`. A CHECK violation's text
    carries the bound phone (Revision 1 item 2).
  - The national spelling (`03123456`) is not matched: it is indistinguishable from other
    digit runs. The API normalises every phone before anything can log it.
- `.env.example`: `PHONE_HASH_SALT=generate_with__openssl_rand_hex_32`, placed after
  `IP_HASH_SALT` (`:26-28`), with a two-line comment: never rotate, never reuse across
  environments.
- **Compose:** `api` and `worker` read `env_file: .env` (`docker-compose.yml:8`, `:50`,
  `:80`), so compose needs no change.
- **CI:** CI copies `.env.example` to `.env` (`.github/workflows/ci.yml:36-37`), so the
  placeholder reaches CI. The production boot check (Q5) never runs there.
- **Test placeholders:** add `"PHONE_HASH_SALT"` to `tests/unit/conftest.py:25-32` and
  `tests/unit/test_health.py:14`.
- `CONTRIBUTING.md` Secrets (`:110-120`): one paragraph and the generate command.

### 3.7 API layer (`ordering/api`)

- `checkout_schemas.py`:
  - a `contact_phone` field validator (D10);
  - `CheckoutOrderRead` gains `estimated_dispatch_at`, `delivery_fee_note`, the address
    snapshot (no contact phone, no hash), `payment_due` and `amount_due_cents`;
  - the phone validator raises `InvalidPhoneNumberError`, whose message never carries the
    number (`core/phone.py:15-19`). The validation handler returns only `loc`, `msg` and
    `type`, never `input` (`api/errors.py:88-91`), so the 422 body cannot echo it;
  - `CheckoutRead.payment` becomes optional.
  - `DELIVERY_FEE_NOTE = "Delivery fee paid to the courier on delivery."` is one constant
    in `ordering/domain/fulfillment.py`, used by responses and emails.
- `checkout.py`:
  - `_translate` (`:116-214`) adds `CashLimitReachedError` → 422
    `CASH_PAYMENT_LIMIT_REACHED` with `reason`;
  - `ConsentRequiredError` carries its field name (`:179-193` hardcodes
    `accept_digital_final_sale`);
  - the cash branch (§2.1);
  - `_RESPONSES` (`:82-103`) and the summary (`:257`) are updated.
- `order_schemas.py`: `amount_due_cents`, `delivery_fee_note`.
  `OrderSummaryView` / `OrderDetailView` (`order_history.py:26-39`) gain
  `amount_due_cents`.
  - The history store's `page` / `get` add one correlated scalar subquery, `live_total`:
    `SUM(line_total_cents) WHERE fulfillment_status <> 'cancelled'`.
  - So the summary page stays one query plus the existing batched payment read
    (`order_history.py:52-54`).

### 3.8 Published interface for VS-029, VS-030, VS-031 (`app.ordering.public`)

| Name | Consumer | Contract |
|---|---|---|
| `amount_due_cents(lines)` | VS-029 handover expected amount, VS-031 "new amount due" email | pure; non-cancelled `line_total_cents` sum |
| `lock_cash_phone(session, phone_hash)` | VS-031 block-inserting cancel | the same lock as checkout; call it **after** the customer's cart lock (ADR-024 d9 `:31`) |
| `cash_block_store(session)` → `SqlCashBlockStore` | VS-031 `insert_block`; VS-029 adds `page(filters)`, `get(id)`, `clear(id, by, at)` (idempotent: an already-cleared block is a no-op) | table and indexes from §4 |
| `hash_phone(e164)` (`app.core.security`) and `normalise_lebanese_phone` (`app.core.phone`) | VS-029 `POST /admin/cash-blocks/search` | normalise, then hash, then match; never store or log the number |
| `CASH_PHONE_LOCK_NS` | tests only | |
| `orders.contact_phone_hash`, `orders.payment_method`, `status = 'in_progress'` | VS-029 cash-due filter and its index; VS-030 "unpaid cash order gives 409" | D8 |
| `Order.estimated_dispatch_at`, `fulfillment_method` | VS-029 emails | |

VS-030 consumes no new function. It reads `payment_method` and the cash payment VS-029
creates. VS-032 consumes `choose_provider` unchanged.

### 3.9 Notices

- `OrderNotices` port. Its adapter `SqlOrderNotices` (`ordering/infrastructure/notices.py`)
  uses `platform.public.SqlOutboxWriter` and `engagement.public.create_notification`, like
  `payments/infrastructure/ordering_side.py:63-85`.
- `cash_order_placed`:
  - template `order_cash_placed`, payload `{order_id, order_number, amount_due_cents,
    currency, fulfillment_method, estimated_dispatch_at, delivery_fee_note,
    pickup: bool}`;
  - a notification of type `ORDER`, event `order.placed`;
  - no phone and no address in the payload, because the outbox is stored.
- Online physical or mixed orders: `SqlPaymentNotices.payment_confirmed`
  (`ordering_side.py:63-85`) adds `fulfillment_method`, `estimated_dispatch_at` and
  `delivery_fee_note` to the `order_payment_confirmed` payload. The STL wording stays.
- `docs/notification-contract.md` lists both.

---

## 4. Database

### 4.1 Is a migration needed?

Yes. One revision, `<new>_cash_payment_blocks_and_cash_settings.py`, with
`down_revision = "8d2f6a1c3e57"`. Every order column VS-028 writes already exists from
VS-023 (`ordering/infrastructure/models.py:131-155`, `:233-234`; ADR-032 `:10`), so there
is no `orders` / `order_items` column change.

**Schema PR first (D2).** PR A contains:

- the migration;
- `CashPaymentBlockModel`;
- the settings registry: three keys added, `free_shipping_threshold` removed
  (`settings_registry.py:167-181`);
- `PublicSettingsRead` and its route docstring;
- `phone_hash_salt` config, `hash_phone`, the boot check, redaction keys, `.env.example`,
  the test placeholders and CONTRIBUTING;
- the settings, schema and reversibility tests.

It contains no checkout code; checkout still refuses physical carts after PR A
(`checkout_rules.py:83-88`).

**Why the registry change goes in PR A:** deleting the row without the registry change
makes `GET /settings/public` raise `SettingNotFoundError` (`settings.py:276-281`).

**Rollout and compatibility:**

- Only the code that predates PR A ever reads the deleted key, and the project has no
  server until the final phase (`vertical-slice-plan.md:59`). So there is no rolling
  window.
- `downgrade()` restores the row, so older code works again after a downgrade.
- Everything else is additive.

### 4.2 Migration contents

1. **`cash_payment_blocks`** (database-design §8.6, `:1186-1214`):
   - `id UUID PK DEFAULT gen_random_uuid()`;
   - `user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT`;
   - `contact_phone_hash TEXT NOT NULL`;
   - `order_id UUID NOT NULL` (FK below);
   - `reason cancel_reason NOT NULL` (existing enum, `create_type=False`);
   - `created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()`;
   - `cleared_at TIMESTAMPTZ NULL`;
   - `cleared_by UUID NULL REFERENCES users(id) ON DELETE RESTRICT`;
   - **Q4:** `order_payment_method payment_method NOT NULL DEFAULT 'cash'` with
     `FOREIGN KEY (order_id, order_payment_method) REFERENCES orders(id, payment_method)
     ON DELETE RESTRICT` (`uq_orders_id_payment_method`, `models.py:167`). This is the
     INV-21 pattern: the database refuses a block for an online order.
   - Constraints:
     - `uq_cash_payment_blocks_order (order_id)`;
     - `ck_cash_payment_blocks_reason`: `reason IN ('refused','no_show')`;
     - `ck_cash_payment_blocks_cash_only`: `order_payment_method = 'cash'`;
     - `ck_cash_payment_blocks_cleared_pair`: `(cleared_at IS NULL) = (cleared_by IS NULL)`;
     - `ck_cash_payment_blocks_hash_format`: `contact_phone_hash ~ '^[0-9a-f]{64}$'`.
   - Indexes: `ix_cash_payment_blocks_user_active (user_id) WHERE cleared_at IS NULL` and
     `ix_cash_payment_blocks_phone_active (contact_phone_hash) WHERE cleared_at IS NULL`.
2. **Settings** (the `75ad58ebd9e5` pattern: a local `sa.table`, literal seed rows,
   `on_conflict_do_nothing`):
   - `cash_payment_enabled` boolean `true`;
   - `cash_max_open_orders` integer `1`;
   - `cash_max_order_total` money `{"amount_cents": 10000, "currency": "USD"}`;
   - DELETE `free_shipping_threshold`.
   - `downgrade()` deletes the three and re-inserts `free_shipping_threshold` with
     `null` and its original description (`de1d8a23512f:130-138`). An admin-set value is
     not restored; it was obsolete and unused.
3. **`orders` CHECKs (Q6):**
   - `ck_orders_contact_phone_e164`: `contact_phone_snapshot IS NULL OR
     contact_phone_snapshot ~ '^\+961[0-9]{7,8}$'` (`core/phone.py:7`);
   - `ck_orders_phone_hash_format`: `contact_phone_hash IS NULL OR contact_phone_hash ~
     '^[0-9a-f]{64}$'`.
   - Every existing row is NULL in both columns (no physical order exists), so a plain
     `ADD CONSTRAINT` validates instantly.
4. **Index (Q3):** `ix_orders_open_cash_phone (contact_phone_hash) WHERE payment_method =
   'cash' AND status = 'in_progress'`. The user side is served by `ix_orders_user_placed`
   (`models.py:202`).

`downgrade()` drops, in reverse: the index, the two CHECKs, the settings rows and the
table.

### 4.3 Registry entries (`settings_registry.py`)

| Key | Type | Default | Range | Public |
|---|---|---|---|---|
| `cash_payment_enabled` | BOOLEAN | `true` | — | yes |
| `cash_max_open_orders` | INTEGER | `1` | 1–10 | no |
| `cash_max_order_total` | MONEY | 10000 | 1–1 000 000 cents | yes |

This matches `docs/settings-registry.md:88-100`. `PUBLIC_KEYS` (`:261`) is derived, so it
follows.

---

## 5. Performance and abuse

- **Hot path cost for cash:**
  - one advisory lock;
  - two indexed EXISTS (partial indexes, tiny tables);
  - one indexed count;
  - three settings reads (cached by the request's session, as `accepting_orders` today).
- **Hot path cost for delivery:** one primary-key `FOR SHARE` read.
- **Contention:** the phone lock serialises only checkouts that share a phone hash
  bucket. The cart lock already serialises one customer.
- **Cash abuse (fake or refused orders):** bounded by `cash_max_open_orders`, matched
  across accounts by phone (BR-145), by `cash_max_order_total`, and by blocks (VS-031).
  A customer can still enter someone else's phone (accepted risk, ADR-024 d6 `:23`).
- **Phone probing:** a customer could learn whether a phone is blocked, or has an open
  cash order, from `cash_blocked` / `open_orders`. Mitigations:
  - it needs a verified account and a filled cart;
  - checkout is limited to 30 per user per hour (`checkout.py:107-117`);
  - the reason never says whether the account or the phone matched (Q8).
- **No new rate limit.**
- **Hash brute force:** Lebanese numbers are about 10^8. Without `PHONE_HASH_SALT` the
  HMAC cannot be reversed; with it, it can be in minutes. The salt is a SecretStr,
  redacted, and never reaches the database or logs (§6.5).
- **EXPLAIN:** `open_order_count` and `active_block` are EXPLAINed in a test with seeded
  rows and `enable_seqscan = off`, to show the partial indexes are usable (nice-to-have,
  §6.2).

---

## 6. Tests (per category; `tests/<category>/…`)

- Priority labels:
  - **[M]** must-have: money, cash limits, races, idempotency, schema;
  - **[N]** nice-to-have: can be cut.
- Blocks are **seeded directly**, since VS-031 inserts them (ADR-024 appendix `:100`).
- Every guard's test is shown to fail once the guard is removed (ADR-032 Consequences
  `:72`).

### 6.1 Unit (`tests/unit/ordering`, `tests/unit/core`, `tests/unit/platform`)

- [M] `resolve_fulfillment`: all five §7.4 rows × `online` / `cash`. Also each invalid
  combination:
  - delivery without an address;
  - pickup with an address;
  - pickup without a phone;
  - STL-only with any fulfillment field;
  - delivery with a `contact_phone`.
- [M] Matrix on kept lines: a mixed cart whose STL is dropped as owned is physical-only
  and may pay cash (Q13).
- [M] `dispatch_days`:
  - 10 units, lead 2, batch 4 → 6;
  - quantity an exact multiple of the batch;
  - lead 0 → 0;
  - max across two lines;
  - STL lines ignored;
  - STL-only → None.
- [M] `cash_precheck` / `cash_limits`:
  - each reason, and the precedence (blocked before open orders before the total);
  - `open == max − 1` passes, `open == max` refuses;
  - `total == max_total` passes, `+1` refuses;
  - `total == 0` refuses.
- [M] `amount_due_cents` excludes cancelled lines.
- [M] D8 invariant: for every combination of terminal line states, with
  `payment_reached_paid = True`, a cash order never derives `IN_PROGRESS`.
- [M] `hash_phone`:
  - a known-answer HMAC vector;
  - `+961 3 123 456`, `03123456` and `9613123456` normalise to one number and one hash;
  - another key gives another hash;
  - 64 lowercase hex characters;
  - a non-E.164 input raises.
- [M] Registry:
  - `free_shipping_threshold` is gone;
  - the three keys have their types and ranges;
  - `cash_max_order_total` of 0, and `cash_max_open_orders` of 0 or 11, are refused.
  - Update `test_settings_registry.py:34`, `:63`, `:214-244`, `:333` and
    `test_deep_properties.py:255`.
- [M] Writer allowlist (D13): a new `test_order_snapshot_writers.py`. An AST and regex scan
  asserts that every `update(OrderModel)` / `UPDATE orders` writes only `status`,
  `updated_at`, `cancelled_at`, `completed_at` or `admin_note`. Today's writers:
  `infrastructure/orders.py:213-219`, `:229-232`.
- [M] **Lock-call order (static, Revision 1 item 1):** `test_cash_lock_order.py` parses
  `place_order` with `ast` and asserts that the calls appear in this order: the cart lock,
  then the address share lock, then `cash.lock_phone`. It also asserts that
  `lock_cash_phone` / `lock_phone` is called from no other function in `src/app`.
  VS-031 extends this allowlist with its cancel, and must show that the cart lock is taken
  first.
- [M] `check_phone_hash_salt`:
  - a 31-character value is refused in `production` and `staging`;
  - a `generate_with__…` value is refused in `production` and `staging`;
  - a 64-hex value passes;
  - both bad values pass in `development` and `test`;
  - the error text never contains the value.
- [M] Log redaction (`tests/unit/test_log_redaction.py` pattern):
  - the five new keys;
  - `+9613123456` and `9613123456` inside a string become `[redacted-phone]`;
  - a 100 kB adversarial digit string is redacted in linear time (the existing
    pattern-speed test);
  - an order number or a UUID is not touched.
- [N] `CheckoutRequest`: the phone is normalised; an invalid phone → `VALIDATION_ERROR`
  at `contact_phone`.

### 6.2 Integration (real Postgres; `tests/integration/ordering`, `…/platform`)

- [M] End to end per cart type, with totals checked (`total == subtotal`,
  `tax == 0`, no shipping):
  - STL-only online (regression);
  - physical delivery online and cash;
  - physical pickup online and cash;
  - mixed delivery online;
  - mixed pickup online;
  - cash refused for STL-only and mixed with `cash_requires_physical`.
- [M] A cash order:
  - has no `payments` row;
  - the provider spy is never called;
  - status `in_progress`, lines `pending`;
  - `cash_terms_accepted_at` is set;
  - the claim is `done` with 201;
  - the cart is cleared;
  - one `order_cash_placed` outbox row (amount due, courier note for delivery) and one
    notification.
- [M] `PAYMENT_PROVIDER=none`:
  - a cash checkout returns 201;
  - an online checkout returns 503 `ONLINE_PAYMENT_UNAVAILABLE`;
  - webhooks are still 404 (ADR-032 d12).
- [M] Cash limits, each refused **with nothing created** (no order, cart intact, claim
  rolled back):
  - switch off;
  - blocked customer;
  - a blocked phone on another account;
  - a second open cash order for the same customer;
  - a second open cash order on another account with the same phone;
  - a total 1 cent over the cap.
- [M] A cart whose snapshot total is under the cap but whose recomputed (live) total is
  1 cent over is refused for cash.
- [M] A cash order with recomputed total 0 → `zero_total`. `PATCH
  cash_max_order_total = 0` → 422.
- [M] The same phone in three spellings, on two accounts, matches the same seeded block
  and the same open-order count.
- [M] An order that stops counting:
  - after it becomes `cancelled` (seeded all-cancelled cash order);
  - after it becomes `completed` (seeded handover).
  Each frees the limit.
- [M] Idempotency:
  - the same key with only `payment_method` changed → 409 `IDEMPOTENCY_KEY_CONFLICT`;
  - the same key and body on cash → stored 201 with `Idempotent-Replayed: true`, and one
    order.
- [M] Cash never selected:
  - `release_candidates_query` (`ordering/infrastructure/orders.py:235-245`);
  - the reconcile candidates (`payments/infrastructure/payments.py:224-225`);
  - retry gives 409 `cash_order` (`ordering/domain/payment_recovery.py:54-55`);
  - manual release gives 409 (`:82-83`).
  Each runs on a real cash order placed through checkout.
- [M] Snapshots survive later edits:
  - edit the address, then delete it; the order is unchanged;
  - change the product's lead time and batch size; the line snapshots are unchanged;
  - the phone is stored E.164;
  - no block row contains a readable phone (`contact_phone_hash` only).
- [M] Address `address_id`:
  - deleted → 422 `INVALID_FULFILLMENT`;
  - another customer's → the same 422, with the same body as unknown.
- [M] Mixed online after verification: the STL line is `awaiting_delivery`, the
  physical lines are `pending`, and `estimated_dispatch_at` is set.
- [M] Mixed **cash** is refused before any lock is taken: no advisory lock appears in
  `pg_locks` (cheap `pg_locks` probe).
- [M] Settings:
  - `free_shipping_threshold` is gone from the table, the registry and
    `GET /settings/public`. The public test asserts
    `"free_shipping_threshold" not in response.json()` (Q11, Revision 1 item 3);
  - the public body has exactly six keys;
  - `GET`/`PATCH /admin/settings/free_shipping_threshold` → 404.
  - Update:
    - `test_public_settings.py:1`, `:25`, `:34`, `:127`;
    - `test_settings_seed.py:19-21`, `:32` (`15` → `17` rows);
    - `test_admin_settings.py:362-374`;
    - `test_deep_vs007_settings.py:106-107`;
    - `tests/unit/platform/test_settings_registry.py:54-63`.
- [M] **Indistinguishable cash refusals (Revision 1 item 4):** two pairs of requests,
  each pair sent with one fixed `X-Request-ID`:
  - `cash_blocked`: customer A blocked by `user_id`, and customer B blocked only by a
    phone match;
  - `open_orders`: customer A with their own open cash order, and customer B whose phone
    matches another account's open cash order.
  Within each pair the response bodies are **byte-identical** (`response.content ==`),
  and the status and `Content-Type` are equal.
- [M] **Boot (Revision 1 item 5):** `tests/integration/test_phone_hash_salt_startup.py`,
  parametrised over `app.main.lifespan` and `app.worker.on_startup` (the
  `test_payment_startup.py:19-35` pattern):
  - `ENVIRONMENT=production` and `staging` with a 31-character salt → `ConfigurationError`;
  - the same with `generate_with__openssl_rand_hex_32` → `ConfigurationError`;
  - a 64-hex salt → boots;
  - `development` and `test` with the placeholder → boots.
- [M] **Q13:** a mixed cart whose STL is already owned checks out cash. The 201 body's
  `dropped_lines` names that STL, and a replay with the same key returns the same
  `dropped_lines`.
- [M] `amount_due_cents`:
  - list and detail on an unpaid cash order;
  - after one line is cancelled (seeded): the remaining live total;
  - null on an online order.
- [M] Schema: every `cash_payment_blocks` constraint refuses its violation:
  - reason `other`;
  - `cleared_at` without `cleared_by`;
  - a second block for one order;
  - a bad hash;
  - a block for an online order (Q4).
  Plus the two new `orders` CHECKs.
- [M] Migration reversibility: extend `tests/integration/test_migration_reversibility.py`
  (up, down, up; the settings row restored on down).
- [M] Lock order (`tests/integration/ordering/test_lock_order.py` pattern): the SQL a
  cash delivery checkout sends is the claim INSERT, the `carts … FOR UPDATE`, the
  `addresses … FOR SHARE`, `pg_advisory_xact_lock`, then reads and INSERTs. There is no
  `orders … FOR UPDATE`.
- [N] `accept_cash_terms` missing for cash → 422 `VALIDATION_ERROR` at that field; online
  ignores it.
- [N] `payment_provider` sent with cash → `provider_not_applicable`.
- [N] Pickup while `pickup_address` is null → `INVALID_FULFILLMENT` (Q16).
- [N] EXPLAIN of `open_order_count` / `active_block` uses the partial indexes.
- [N] The `order_payment_confirmed` payload for a delivery order carries
  `delivery_fee_note` and `estimated_dispatch_at`.

### 6.3 Concurrency (`tests/concurrency/test_cash_checkout_races.py`; `meet_or_fail`, `tests/concurrency/barrier.py:22`)

- [M] **R1, two accounts, one phone:** both check out in parallel with
  `cash_max_open_orders = 1` → exactly one order and one 422
  `CASH_PAYMENT_LIMIT_REACHED`. Run with pickup (entered phone) and with delivery (address
  phones that are spellings of one number).
- [M] **R2, one customer, two keys:** two cash checkouts in parallel → one order and one
  409 `CART_EMPTY` (the race-1 shape, `test_checkout_races.py:97`).
- [M] **R3, cash checkout versus VS-031 block insert (real Postgres, Revision 1 item 1):**
  two sessions on the test database, coordinated by `meet_or_fail`.
  - **The stand-in cancel**, `tests/concurrency/cash_block_support.py`, uses the lock
    order VS-031 will use (`ADR-024:31`):
    - `lock_order_for_change` (orders, then lines);
    - the customer's cart `FOR UPDATE`;
    - `lock_cash_phone`;
    - `insert_block`.
    It has no refund step (no `refunds` table yet).
  - **Variant a:** another account with the same phone. The cancel takes the phone lock
    and pauses at a barrier; the checkout starts and must block on the lock (asserted
    through `pg_locks`: one `advisory` lock not granted); then the cancel commits. The
    checkout gets 422 `PAYMENT_METHOD_NOT_ALLOWED` (`cash_blocked`) and creates nothing.
  - **Variant b:** the same order of events, for the same customer with a different
    phone. The checkout blocks on the **cart** lock instead, and is then refused the same
    way (a `user_id` match).
  - **Variant c:** the reverse. The checkout holds the phone lock at a barrier, and the
    cancel blocks on it, or on the cart in variant b. The checkout commits its order
    first, then the block is inserted. One order and one block, which is the permitted
    order.
  - Every variant, repeated 20 times:
    - never an order committed after a block that matches it;
    - never `deadlock_detected` (SQLSTATE `40P01`);
    - each session finishes within `lock_timeout = 5s`.
- [M] **R4, address delete versus delivery checkout:** either the order (snapshot of the
  pre-delete row) or 422. Never a 500 or a deadlock.
- [M] **R5, no cycle with payment paths:** a cash checkout for user U runs in parallel
  with webhook verification, `release_stale` and payment retry on U's other (online)
  order. Every outcome is correct and `deadlock_timeout` never fires.
- [N] **R6:** a cash checkout races `PATCH cash_payment_enabled = false`. Either the order
  is placed first or it is refused.

### 6.4 Contract

- [N] `docs/frontend-handoff/openapi.json` regenerated. A snapshot diff lists only the
  intended changes: `CheckoutRead.payment` nullable, the new order fields, the
  `PublicSettingsRead` fields, the new 422 code.

### 6.5 Security (`tests/security/`)

- [M] **Phone and hash scan (Revision 1 item 2):**
  `tests/security/test_contact_phone_never_leaks.py`, on the `app_logs` capture of
  `tests/integration/test_deep_logs_and_leaks.py` (which first asserts that events were
  captured, so absence cannot pass vacuously).
  - **Driver:** one sentinel phone, `+96171999888`, sent as `71 999 888` and as
    `+961 71 999 888`, through:
    - every §7.4 row × payment method;
    - every cash refusal (`cash_disabled`, `cash_blocked` by account and by phone,
      `open_orders`, `order_total`, `zero_total`);
    - an invalid phone (`VALIDATION_ERROR`);
    - a replay, and an idempotency conflict;
    - a forced `ck_orders_contact_phone_e164` violation, to cover the database-error log
      path.
  - **Needles:**
    - the E.164 form;
    - the national digits `71999888`;
    - `96171999888`;
    - the phone's 64-hex hash;
    - `PHONE_HASH_SALT`'s value.
  - **Haystacks, all of which must contain no needle:**
    - every response body and header;
    - every captured log line;
    - `audit_logs.before_data` / `after_data`;
    - `email_outbox.payload`;
    - `notifications.payload`;
    - `idempotency_records.response_body`.
  - **Allowlist (Q17):** `GET /api/v1/me/orders/{id}`'s `contact_phone` field may hold
    the E.164 form, and nothing else. The scan asserts that the needle occurs exactly
    there and nowhere else in that body. `cash_payment_blocks` and `orders` are the only
    tables allowed the hash, and `orders` the only one allowed the number.
- [M] No row of `cash_payment_blocks` contains the plaintext phone (covered above,
  stated separately because it is the anonymisation guarantee, ADR-024 d6).
- [M] `PHONE_HASH_SALT` never appears in logs, responses or the database
  (`test_ip_salt_never_leaks.py` pattern).
- [M] A foreign `address_id` gives the same 422 body as an unknown one.

### 6.6 Smoke and e2e

- [M] e2e: register, verify, add a physical product, cash pickup → 201. The order shows
  `in_progress`, `payment_due: true` and `amount_due_cents` equal to the total.
- [N] e2e: delivery, online, pay through the mock → paid; the physical line is `pending`;
  dispatch is shown.

### 6.7 Running the suite

Sequential chunks, never all at once (`VS-024-payment-recovery-plan.md` §6.7): unit;
integration/ordering; integration/platform; integration/payments; concurrency; security;
e2e and smoke. **No tests run in this planning step.**

### 6.8 The nice-to-have [N] tests (cuttable)

Cutting any of these leaves every money, cash-limit, race, idempotency, leak and schema
guarantee covered by an [M] test.

1. §6.1: `CheckoutRequest` normalises the phone; an invalid phone → `VALIDATION_ERROR` at
   `contact_phone`. The leak scan exercises the same path, but asserts only absence.
2. §6.2: `accept_cash_terms` missing for cash → 422; online ignores it. The CHECK
   `ck_orders_cash_terms` still guards the database.
3. §6.2: `payment_provider` sent with cash → `provider_not_applicable` (Q2).
4. §6.2: pickup while `pickup_address` is null → `INVALID_FULFILLMENT` (Q16).
5. §6.2: EXPLAIN of `open_order_count` / `active_block` uses the partial indexes.
6. §6.2: the `order_payment_confirmed` payload for a delivery order carries
   `delivery_fee_note` and `estimated_dispatch_at`.
7. §6.3 R6: a cash checkout races `PATCH cash_payment_enabled = false`.
8. §6.4: the openapi snapshot diff.
9. §6.6: the e2e delivery, online, mock-paid order.

---

## 7. Docs and ADRs

- **ADR-038** "Physical checkout and cash eligibility" (new), plus its line in
  `docs/adr/README.md:44`. Decisions:
  - D3, which **amends ADR-032 d12** (`ADR-032:44`): `PAYMENT_PROVIDER=none` means no
    online payment; cash checkout still works.
  - D4, D5 and D6, including the invariant that no path holding a cart lock waits on an
    existing `orders` row. VS-031's `orders → cart → phone` cancel depends on it (§8.1).
  - D7, D8 (with the "no edge out of delivered/picked_up" condition), D10, D11 and D13.
  - The answers to §10.
- `docs/checkout.md`: physical, delivery, pickup, cash, the matrix, refusals, the
  one-transaction cash flow, the lock order (`:92-94`).
- `docs/requirments/api-endpoints.md`:
  - `CheckoutRequest` rules (`:858-869`);
  - `CheckoutRead` (`:1283-1293`), with `payment` nullable and the new order fields;
  - the §5.2 reasons;
  - the row at `:369` "As built".
- `docs/requirments/database-design.md`: §8.6 (the `order_payment_method` column and FK,
  if Q4), the `orders` CHECKs and index (`:1029`, `:1054`).
- `docs/settings-registry.md`: the "not seeded yet" text (`:88`) becomes seeded; the
  allowlist (`:120`, `:134-142`) and the count (`:105`).
- `docs/order-history.md:32`: `amount_due_cents` is built.
- `docs/address-book.md:48`: checkout locks `FOR SHARE`.
- `docs/notification-contract.md`: `order_cash_placed` and the new
  `order_payment_confirmed` fields.
- `docs/frontend-handoff/openapi.json` and `BACKEND-RESPONSE.md:288-310`, `:1158` (PR A):
  the example body at `:288` loses the field and gains the two cash keys. The table row at
  `:307` and the note at `:310` are replaced by a dated entry:
  > **2026-10-20 (VS-028 PR A): `free_shipping_threshold` removed** from
  > `GET /api/v1/settings/public` and from the admin settings (404). `cash_payment_enabled`
  > (bool) and `cash_max_order_total` (`{amount_cents, currency}`) added. Remove any read
  > of the old field.

  `:1158` changes from "will be deleted by later slices" to "deleted 2026-10-20 (VS-028)".
  PR B adds a second dated entry for the checkout changes: `payment: null` for cash, the
  new order fields, and the new 422 code.
- `docs/vertical-slice-plan.md`: the VS-028 status (`:694`) and the table row (`:33`).
- `CONTRIBUTING.md` (Secrets) and `.env.example`.

---

## 8. Implementation steps, in order, with checkpoints

### PR A: schema, settings and secret (branch `vs-028-schema`; merge first, under the migration lock)

1. Announce the migration lock. Re-derive the head; it must still be `8d2f6a1c3e57`.
2. Migration §4.2, with `CashPaymentBlockModel`.
3. Registry §4.3; `PublicSettingsRead`; update the settings tests listed in §6.1–6.2.
4. `phone_hash_salt`, `hash_phone`, the boot check, redaction, `.env.example`, the test
   placeholders and CONTRIBUTING.
5. Schema, reversibility, registry and `hash_phone` tests.

**PR A's exact file list** (nothing else may change; the PR description repeats it):

| # | File | Change |
|---|---|---|
| 1 | `migrations/versions/<rev>_cash_payment_blocks_and_cash_settings.py` | **new**, §4.2, `down_revision = "8d2f6a1c3e57"` |
| 2 | `src/app/ordering/infrastructure/models.py` | `CashPaymentBlockModel`; the two `orders` CHECKs and the partial index in `OrderModel.__table_args__` (`:165-204`), so `test_model_migration_parity.py` passes |
| 3 | `src/app/platform/domain/settings_registry.py` | three entries added, `free_shipping_threshold` removed (`:167-181`) |
| 4 | `src/app/platform/api/schemas.py` | `PublicSettingsRead` (`:124-143`) |
| 5 | `src/app/platform/api/settings.py` | docstring "five" → "six" (`:263-275`) |
| 6 | `src/app/core/config.py` | `phone_hash_salt: SecretStr` |
| 7 | `src/app/core/security.py` | `hash_phone`, `check_phone_hash_salt` |
| 8 | `src/app/core/logging.py` | five keys, the phone pattern |
| 9 | `src/app/main.py` | `check_phone_hash_salt(settings)` beside `:31` |
| 10 | `src/app/worker.py` | the same beside `:42` |
| 11 | `.env.example` | `PHONE_HASH_SALT` |
| 12 | `CONTRIBUTING.md` | Secrets paragraph |
| 13 | `docs/settings-registry.md` | seeded keys, the allowlist, the counts |
| 14 | `docs/requirments/database-design.md` | §8.6 column, FK and CHECKs; the `orders` CHECKs and index |
| 15 | `docs/frontend-handoff/BACKEND-RESPONSE.md` | the dated removal entry (§7) |
| 16 | `docs/frontend-handoff/openapi.json` | `PublicSettingsRead` only |
| 17 | `tests/unit/conftest.py` | `PHONE_HASH_SALT` placeholder |
| 18 | `tests/unit/test_health.py` | the same |
| 19 | `tests/unit/core/test_phone_hash.py` | **new**: `hash_phone`, `check_phone_hash_salt` |
| 20 | `tests/unit/test_log_redaction.py` | new keys and the phone pattern |
| 21 | `tests/unit/platform/test_settings_registry.py` | `:34`, `:54-63`, `:214-244`, `:333`, plus the new keys |
| 22 | `tests/unit/test_deep_properties.py` | `:255` moves to `cash_max_order_total` |
| 23 | `tests/integration/platform/test_public_settings.py` | six keys; asserts the field is absent |
| 24 | `tests/integration/platform/test_settings_seed.py` | `:19-21`, `:32` (17 rows) |
| 25 | `tests/integration/platform/test_admin_settings.py` | `:362-374` re-targeted; old key → 404 |
| 26 | `tests/integration/platform/test_deep_vs007_settings.py` | `:106-107` re-targeted |
| 27 | `tests/integration/ordering/test_cash_payment_blocks_schema.py` | **new**: every block and `orders` CHECK |
| 28 | `tests/integration/test_migration_reversibility.py` | up/down/up; the table and the restored row |
| 29 | `tests/integration/test_phone_hash_salt_startup.py` | **new**: the boot test (§6.2) |
| 30 | `tests/security/test_phone_hash_salt_never_leaks.py` | **new**: the salt never in logs, responses or the database (`test_ip_salt_never_leaks.py` pattern) |

**Checkpoint 1:** PR A green and merged; the lock is released. Report the migration id,
the test counts and the diff of the public settings body.

### PR B: code (branch `vs-028-physical-checkout`, from `main` after PR A)

6. Pure rules §3.1, with their unit tests (including the D8 invariant).
7. Catalog `CartProduct` §3.2; Identity `lock_checkout_address` §3.3.
8. `SqlCashChecks` / `SqlCashBlockStore` §3.5; the `SettingsSource` additions.
9. `place_order` §3.4; delete `require_digital_only` / `require_online`.
10. Route and schemas §3.7; `SqlOrderNotices` §3.9.

**Checkpoint 2:** the §6.2 [M] matrix, cash, limits and idempotency tests are green.
Report any precedence change in the existing `test_checkout_api.py` refusals
(`:403-442`).

11. The payment email payload; `amount_due_cents` in order history.
12. Concurrency §6.3, lock order, security §6.5, and the snapshot writer test.

**Checkpoint 3:** all [M] tests are green in sequential chunks. Report each guard shown
failing once removed.

13. Docs and ADR-038 §7; regenerate openapi.

**Checkpoint 4:** owner review of ADR-038 and the docs diff, then merge.

### 8.1 Lock order per path (resolves item 2)

- **Global order** (ADR-036 d14, `ADR-036:43`):
  `idempotency_records → carts → orders → order_items (by id) → payments (by id) →
  webhook_events`, then INSERTs, and the alert advisory lock last.
- **VS-028 places two new locks between `carts` and `orders`:** `addresses` (`FOR SHARE`)
  and the phone advisory lock, in that order. This is the ADR-024 d9 row "Cash checkout:
  cart → phone advisory lock → INSERT order" (`ADR-024:39`).

**The ADRs and this plan, side by side** (Revision 1 item 1; quotes are verbatim):

| Source | Quoted order | This plan | Same? |
|---|---|---|---|
| ADR-024 d9 preamble (`ADR-024:26`) | "Every write that changes an order's lines, payment or refunds locks the `orders` row first (`FOR UPDATE`), then the lines it reads or changes in `id` order, then the payment row" | Checkout changes no existing order. It only INSERTs new rows, so no `orders` lock is taken | yes (it does not apply) |
| ADR-024 d9, "Cash checkout" (`ADR-024:39`) | "cart → phone advisory lock → INSERT order (no existing `orders` row is locked)" | claim → **cart** → address `FOR SHARE` (delivery only) → **phone advisory lock** → INSERT order | yes. The address is the one addition; it sits between cart and phone, and both the cart and the phone keep their relative order |
| ADR-024 d9, "Customer self-cancel, admin cancel" (`ADR-024:31`) | "`orders` → all physical lines by `id` → `payments` → INSERT refund rows → (if a block may be inserted) the customer's cart → phone advisory lock → recompute" | VS-031's block insert: `orders` → lines → (`payments`, refunds once VS-030 exists) → **cart** → **`lock_cash_phone`** → INSERT block. The R3 stand-in uses it exactly | yes |
| ADR-036 d14 (`ADR-036:43`) | "`idempotency_records → carts → orders → order_items (by id) → payments (by id) → webhook_events`, then INSERTs, and the alert advisory lock last" | `idempotency_records` → `carts` → `addresses` → phone lock → INSERTs only | yes. `addresses` and the phone lock come after `carts` and before any `orders` row, and checkout takes no alert lock |

**Confirmed: no path takes the phone lock before the cart lock or the address lock.**

- **Checkout:** `place_order` calls `cash.lock_phone` only in step 9 (§3.4). That is after
  the cart lock (step 3) and the address share lock (step 5). Online orders never call it.
- **VS-031 cancel:** the only other caller, after the customer's cart lock (`ADR-024:31`).
  It takes no address lock.
- **Nothing else** calls it: VS-029's handover and block clear, webhook verification,
  reconciliation, release and retry.
- **Enforcement:**
  - the static call-order test (§6.1) fails if the order changes or a new caller appears;
  - the SQL-order test (§6.2) fails if the statements reach Postgres in another order;
  - R3 (§6.3) proves the behaviour on real Postgres.

| Path | Order |
|---|---|
| Cash checkout (VS-028) | claim (INSERT/SELECT `idempotency_records`) → `carts` FOR UPDATE → `addresses` FOR SHARE (delivery) → phone lock → unlocked reads (`settings`, blocks, open count) → INSERT `orders`, `order_items`, history, audit, outbox, notification → DELETE `cart_items` → UPDATE own claim |
| Online checkout, physical (VS-028) | claim → `carts` → `addresses` FOR SHARE (delivery) → INSERTs incl. `payments`. **No phone lock** (online is not limited) |
| Webhook verify / reconcile Tx B / manual confirm | `orders` → `order_items` by id → `payments` → `webhook_events` → alert lock (`ADR-032:57`) |
| `release_stale_checkouts` | `orders` → lines → `payments` |
| Payment retry | claim → `orders` (owned) FOR UPDATE → INSERT `payments` (`ADR-036:39`) |
| Address PATCH / DELETE / default | `users` FOR NO KEY UPDATE → `addresses` rows |
| VS-031 block-inserting cancel | `orders` → lines → `payments` → INSERT refunds → **the customer's `carts`** → **phone lock** → INSERT block (`ADR-024:31`) |
| VS-029 handover | `orders` → lines → INSERT `payments` |

**No cycle.** A deadlock needs a cycle in which each transaction waits for a lock the
next one holds.

1. **Checkout locks no existing `orders` or `payments` row.** Its foreign-key checks take
   `FOR KEY SHARE`:
   - on the order row it just inserted (its own);
   - on `users` (`orders.user_id`): compatible with an address writer's
     `FOR NO KEY UPDATE`;
   - on `products`.
   A product editor's `FOR UPDATE` (`catalog ports.py:39-41`) holds no cart, order,
   address or phone lock, so it cannot close a cycle.
2. **Every path that takes `orders` first** (verify, release, retry, handover, cancel)
   either never takes a cart or phone lock, or takes them after `orders` (cancel). If
   checkout waits on cancel's cart or phone lock, cancel waits on nothing checkout holds:
   - cancel's later steps are INSERTs of a block and refunds, with foreign keys to its own
     order and to `users`;
   - checkout holds only carts, addresses, the phone lock and its own new rows.
3. **Two checkouts** order cart before phone, and one customer's two checkouts serialise
   on the cart. Two cancels order cart before phone and lock different orders. A checkout
   and a cancel order cart before phone (point 2).
4. **Addresses** are locked only by checkout (share, after carts) and by address writers
   (exclusive, after `users`). Address writers take no cart, phone or order lock.
5. **Invariant recorded in ADR-038:** no path holding a cart lock may wait on an existing
   `orders` row. Breaking it (for example VS-041 locking an order while holding a cart)
   would create a cycle with VS-031's `orders → cart` order, and VS-041's plan must
   re-check this.

The §6.3 R3 and R5 tests and the §6.2 SQL-order test exercise points 1–3.

**R1 proof (two accounts, one phone).**

- A (user U) and B (user V) hold their own carts, then both request
  `lock_cash_phone(h)`. B waits.
- A counts 0, inserts its order and commits; the transaction-scoped lock is released at
  COMMIT.
- B's next statement (the count) runs in Read Committed with a fresh snapshot, so it sees
  A's committed `in_progress` cash order with `contact_phone_hash = h`. It counts 1 and
  refuses.
- If A rolls back, B counts 0 and proceeds: correct.

**Block race (VS-031).** The cancel inserts the block under the same phone lock, and
under the customer's cart lock. So:

- a checkout by another account with that phone is serialised by the phone lock;
- a checkout by the same customer with a different phone is serialised by the cart lock
  (`vertical-slice-plan.md:893`).

Checkout reads blocks only after taking both locks.

---

## 9. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | A leaked `PHONE_HASH_SALT` lets the about 10^8 Lebanese numbers be brute-forced from block hashes. | SecretStr, redaction, boot check, never in the database; CONTRIBUTING guidance. |
| R2 | The salt must never rotate. Losing it breaks phone matching for every block. | Orders keep `contact_phone_snapshot`, so order hashes can be recomputed with a new salt. Blocks keep `user_id` matching. ADR-038 records the recovery procedure. |
| R3 | D8 relies on "no edge out of delivered/picked_up". A future slice (VS-029b, returns) adding one would let a paid cash order count as open. | The D8 unit test fails on such a change; ADR-038 names the condition. |
| R4 | The `PublicSettingsRead` field removal breaks a frontend still reading `free_shipping_threshold`. | The handoff already says to treat it as absent (`BACKEND-RESPONSE.md:310`). |
| R5 | `CheckoutRead.payment` becomes nullable; a client that assumes a redirect breaks on cash. | Documented in openapi and the handoff; cash is new, so no existing client sends it. |
| R6 | Error precedence shifts for online carts with fulfillment fields (today: 422 `INVALID_FULFILLMENT` before price checks, `checkout.py` service `:84`). | Checkpoint 2 reports every changed precedence. |
| R7 | The address `FOR SHARE` lock blocks an address edit for the length of checkout Tx1. | Tx1 holds no network call (ADR-032 d8), so the wait is milliseconds. |
| R8 | A customer enters someone else's phone for pickup cash, which consumes that person's cash allowance. | Accepted in ADR-024 d6 (`:23`); the administrator calls before printing and can clear the block. |
| R9 | Settings rows missing after a bad restore make cash checkout 500 (`settings_reader.py:52-58`). | Fail closed is intended: a deployment fault, not a customer error. |

---

## 10. Owner questions (each with a recommendation)

**Answered 2026-10-20 (Revision 1):** Q1–Q16 as recommended. Q13 adds that the dropped
STL is still named in `dropped_lines`. **Q17 decided in Revision 2.**

1. **Delivery with a `contact_phone` sent:** refuse or ignore? **Recommend refuse** (422
   `INVALID_FULFILLMENT`). The delivery phone is the address's (BR-078); ignoring a sent
   field hides client bugs.
2. **`payment_provider` sent with cash:** **recommend refuse** with 422
   `PAYMENT_METHOD_NOT_ALLOWED` (`provider_not_applicable`), in the spirit of
   `extra="forbid"`.
3. **The `contact_phone_hash` partial index now, or after EXPLAIN shows the need?**
   **Recommend now** (§4.2.4). The table is empty, so creating it is free, and EXPLAIN on
   an empty table cannot show the need.
4. **The composite FK on `cash_payment_blocks` (`order_payment_method = 'cash'`):** it
   adds a column database-design §8.6 does not list. **Recommend yes:** the database then
   refuses a block for an online order, as INV-21 / INV-22 do for payments.
5. **`PHONE_HASH_SALT` required with no default, plus a boot refusal of a short or
   placeholder value outside development/test?** **Recommend yes to both.** A default
   would silently create hashes nobody can recompute.
6. **Format CHECKs on `orders.contact_phone_snapshot` and `contact_phone_hash`?**
   **Recommend yes.** The hash must match exactly across accounts, so a wrong spelling in
   the database would defeat the limit.
7. **Dispatch in calendar days from `placed_at`, or working days?** **Recommend calendar
   days, as a timestamp** (`placed_at + N days`). SRS §8.6 says "days" with no calendar
   (`SRS.md:720`), and BR-038 promises only an estimate.
8. **Refusal reasons:** distinct `cash_blocked` / `open_orders` / `order_total`, or one
   generic `cash_unavailable`? **Recommend distinct reasons that never say whether the
   account or the phone matched.** Checkout must explain why cash is unavailable
   (`settings-registry.md:99-100`).
9. **Snapshot immutability: a static writer test, or a database trigger?** **Recommend
   the static test** (D13). It matches `test_order_item_writers.py`, and a trigger would
   also block VS-045's anonymisation of these columns.
10. **The cash placement email:** a new template `order_cash_placed`? **Recommend yes**,
    with no phone or address in the payload. Online physical orders extend
    `order_payment_confirmed` instead.
11. **Remove `free_shipping_threshold` from the public response in PR A (a breaking field
    removal)?** **Recommend yes**, as the slice and the handoff already announce.
12. **`amount_due_cents` as a bare integer (the owner decision's wording), or as a
    `PriceRead`?** **Recommend the bare `amount_due_cents`**, as decided on 2026-10-19,
    with the currency read from `total.currency`.
13. **A mixed cart whose STL is dropped as already owned:** may the now physical-only
    order pay cash? **Recommend yes:** the matrix runs on the kept lines, and the order
    holds only physical lines.
14. **Should online physical orders also take the phone lock?** **Recommend no.** Online
    orders are not limited, and the lock would only add contention.
15. **The phone in the audit row of `order.placed`?** **Recommend never** (neither the
    number nor the hash). The order row holds the snapshot, and audit rows outlive
    anonymisation.
16. **Pickup while `pickup_address` is not configured (null, SRS §30.2):** **recommend
    refusing pickup** with 422 `INVALID_FULFILLMENT`. A customer must not choose a pickup
    location that has not been published.
17. **Where may the plaintext contact phone appear in an API response?** (Revision 1,
    item 2.) "Never" would break two responses that are already built, and one that is
    planned:
    - VS-025's `OrderDetailRead.contact_phone` (`ordering/api/order_schemas.py:149`,
      `:177`), the customer's own order;
    - the address book's own `phone` (`api-endpoints.md:793-810`);
    - VS-029's admin order detail, which needs it to call the customer before printing
      (`api-endpoints.md:558`).

    **Recommend:** the hash never appears in any response. The number appears in no
    VS-028 response, and only in these three owner or admin reads. The scan test
    allowlists them by route and asserts that they are the only occurrences. The
    alternative is to mask it in `OrderDetailRead` (`+961 71 •••888`), a VS-025 contract
    change for the frontend.
