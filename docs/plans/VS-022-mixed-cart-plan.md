# VS-022 — Mixed Cart: Implementation Plan

**Status:** IN PROGRESS (implementation started on branch `vs-022-mixed-cart`)
**Date:** 2026-10-16
**Planned against alembic head:** `75ad58ebd9e5` (ip_hash_salts_and_retention_settings,
VS-046). Derived statically from `revision`/`down_revision` in `migrations/versions/`:
18 files, one linear chain, one head, no merge revisions. It matches the expected head.
The chain ends `… → 2e89860f5274` (VS-026) `→ 58aac63240fc` (VS-038) `→ 75ad58ebd9e5`.
This slice's migration therefore has `down_revision = "75ad58ebd9e5"`. Re-derive it
immediately before `alembic revision`, because another slice may merge first.

## Revision 1 (2026-10-16): answers to the plan review

Every answer below was checked against `main` at `4144158`. Each is reflected in the
section named.

1. **`products.type` never changes after creation** (§4).
   - The only writes of `type` are INSERTs:
     - `ProductRepository.add` (`src/app/catalog/infrastructure/product_repository.py:87`);
     - `scripts/dev_seed.py:360`, which goes through the same admin create command;
     - the column's creation in `fc18b48a1780_products_table.py:79`.
   - The only UPDATE is `save_if_version` (`product_repository.py:100-117`). It writes
     `_columns(product.attributes)` (`:43`), and `ProductAttributes` has no `type`
     field (`src/app/catalog/domain/product.py:51`: "`type` is not here: it is
     immutable").
   - `AdminProductUpdate` refuses `type` through `extra="forbid"`
     (`src/app/catalog/api/product_schemas.py:133-134`).
   - No migration updates it.
   - The composite FK is declared `ON UPDATE RESTRICT`, so any future type change on a
     product in a cart is **blocked** (`23503`), never cascaded. Nothing ever rewrites
     `cart_items.product_type`, so `ck_cart_items_stl_quantity_one` cannot fail as a
     side effect of a product update.
   - **Keep the FK.** It costs one index on a small table, it costs no write path
     anything, and it turns the domain-only immutability into a DB guarantee that
     VS-023's ownership index can rely on.
2. **Creating the cart on the first add** (§3.5, §6): `INSERT … ON CONFLICT (user_id)
   DO NOTHING`, then `SELECT … FOR UPDATE`.
   - Under READ COMMITTED both concurrent first adds succeed. The second waits on the
     first's uncommitted row, gets `DO NOTHING`, then blocks on `FOR UPDATE` and reads
     the committed row.
   - A new concurrency test covers two first adds of *different* products: both 200,
     one cart, two lines.
3. **The purchasable decision has one owner** (§3.1).
   - The SQL side: Storefront visibility is `_VISIBLE` in
     `src/app/catalog/infrastructure/storefront_query.py:57-62`, which is private. It is
     promoted to one shared function, `listed_predicate()`, in a new
     `catalog/infrastructure/visibility.py`. `storefront_query._base()` and the new
     `SqlCartProductReader` both call it, so there is no copy.
   - The rule side: `purchase_refusal()` in `catalog/domain/storefront.py` wraps the
     existing `capabilities()` (`storefront.py:142-151`).
   - The first draft said "mirrors… reuse rather than copy" without naming the shared
     function. That is now fixed.
4. **`over_cap` flag** (§2, §3.2, §3.6). It replaces the draft's
   `quantity_exceeds_limit`: true when the line's quantity is above the product's
   *current* cap. Checkout must refuse such a line with `422 QUANTITY_EXCEEDS_LIMIT`.
5. **The snapshot price is display-only** (§3.6). Checkout charges the live
   `products.price_cents`, read and totalled server-side. The snapshot serves only the
   `CART_PRICE_CHANGED` comparison.
6. **Lock order quoted and compared** (§3.6): compatible with ADR-024 decision 9 and
   with the VS-004 / ADR-018 order. See the comparison table in §3.6.
7. **Rate limit** (§3.7, §5). It uses `enforce_rate_limit`
   (`src/app/core/rate_limit.py:19`), which is keyed on an arbitrary `subject`. The
   IP-keyed wrapper `rate_limiter` (`:66`, `subject=client_ip` at `:78`) is **not**
   used. The per-user limit passes `subject=str(user.id)` from `current_verified_user`,
   exactly as `src/app/engagement/api/wishlist.py:105` does.
8. **ADRs on `main`:** ADR-001 to ADR-028 plus `README.md` (`docs/adr/`). No remote
   branch has a higher number. **ADR-029 is the next free number** (§7).

**Earlier decisions changed by this revision:**
- **The cart lock is `FOR UPDATE`, not `FOR NO KEY UPDATE`.** The review asked for it,
  and nothing loses by it: only the lock holder writes `cart_items`, so the stronger
  lock blocks no foreign-key check.
- **`quantity_exceeds_limit` is renamed `over_cap`.** It is now computed whenever the
  product row exists, including when the product is not listed.
- **Q9's wording is corrected.** Cart code takes no *explicit* product lock. A
  `cart_items` insert does take an implicit `KEY SHARE` on `products` and on `users`
  through its foreign keys; §3.6 shows this cannot cycle.

## Revision 2 (2026-10-16): Q6 tightened, owned-STL exception, isolation level

**SRS §7.3, verbatim** (`docs/SRS.md:650-665`, the relevant steps):

> ### 7.3 Checkout Validation Sequence
> Executed inside a single transaction:
> 3. Lock the cart.
> 4. Validate every line: product exists, not deleted, visible, available, purchase mode permits online sale.
> 5. Re-verify STL ownership (a paid, unrefunded STL line); silently drop anything acquired since adding.
> 6. Validate quantities against current caps.

**What the SRS says about owned STLs, and what this plan does with it:**
- Step 5 (`SRS.md:658`) **explicitly** drops an STL acquired since adding. So the
  single exception is kept: VS-023 may drop *only* an STL that became owned after it
  was added.
- **The customer must be told which line was dropped.** The checkout response names the
  dropped product ids. The SRS word "silently" is read as "without failing the
  checkout", not "without telling the customer".
- Adding an already-owned STL stays a refusal, `409 PRODUCT_ALREADY_OWNED` (BR-025
  `SRS.md:199`, §7.1 `:643`, INV-08 `:1125`, ADR-025).
- The plan row's own wording also allows a 409 when the ownership index fires during
  checkout (VS-023 "Logic").

**Q6, tightened.** A line that is not purchasable (`not_listed`, `unavailable`,
`whatsapp_only`) or is `over_cap` is **never dropped silently**. Checkout refuses with
422 and names every offending line (§3.6). This is the owner's decision of 2026-10-16,
pending the co-owner's confirmation (Q14).

**Isolation level:** now stated in §3.5 (READ COMMITTED, the default; never
overridden).

**Migration target, for step 5:**
- `migrations/env.py:25` sets the URL from `get_settings().database_url`.
- `Settings` reads it from the process environment, or else from `.env`
  (`src/app/core/config.py:8,20`).
- `.env.example:16` points at `postgres:5432`, the compose-network hostname. That does
  not resolve from the Windows host. The real `.env` was not read, so what the host
  venv would target is UNVERIFIED.
- Run migrations the CONTRIBUTING way, inside the network: start the stack (`docker
  compose up -d postgres redis api`), then `docker compose exec api alembic …`, which
  targets the compose `postgres` service and its `pgdata` volume.
- Alternatively, run from the host venv with an explicit
  `DATABASE_URL=postgresql+asyncpg://…@localhost:5442/…` (the host port mapping in
  `docker-compose.yml:13`).
- Either way, the compose stack must be running.

## 0. Preflight

- `git fetch`, `git checkout main`, `git pull --ff-only`: already up to date. HEAD is
  `4144158` (merge of PR #14, VS-046) and the working tree is clean.
- `git branch -r` lists `origin/main`, `origin/feat/vs-038-wishlist` and
  `origin/vs-046-security-retention`. None mentions VS-022, cart or basket.
- `git log --oneline -10` covers only VS-046 (`039b7b0` … `4144158`). No commit touches
  VS-022, cart or basket. Across all history the only "cart" match is `8b16928` (ADR-025
  docs), which describes the future `409 PRODUCT_ALREADY_OWNED`.
- In the code, `src/app/ordering/` is an empty skeleton (`api`, `application`, `domain`,
  `infrastructure`, each with only `__init__.py`). `tests/integration/ordering/` and
  `tests/unit/ordering/` exist but are empty. No `carts` or `cart_items` table exists.
  The only "cart" text in `src/` is two docstrings in Catalog's storefront code that
  defer to the future cart.
- `docs/plans/` held no VS-022 plan before this file.

**Sources read for this plan:**
- `docs/vertical-slice-plan.md`: VS-022, VS-023, VS-023b, VS-024, VS-028, VS-029, the
  Definition of Done and Rules.
- `CONTRIBUTING.md`: the migration lock and the PR rules.
- `docs/SRS.md`: BR-001–027, §6.5, §7.1–7.3, §14.2, INV-07–09 and §21.2.
- `docs/requirments/`:
  - `api-endpoints.md` §5, §10.1, §10.3, §29.4 and `CartRead`;
  - `database-design.md` §8.1, §8.2, §15.3, §16, §25 and the retention table;
  - `entities-and-business-rules.md` (Cart, CartItem);
  - `functional-requirements.md` FR-05;
  - `domain-glossary.md`.
- ADRs 008, 011, 022, 024 (decision 9, lock order), 025, 027 and 028.
- Code: `docs/storefront-catalogue.md`, and the VS-038 and VS-026 code and plan.
- Real models: `ProductModel` (`src/app/catalog/infrastructure/models.py:192`) and
  migration `fc18b48a1780_products_table.py`.
- Tests: `tests/unit/test_deep_architecture.py` and
  `tests/integration/test_deep_db_constraints_and_migrations.py`.

## 1. Scope and non-goals

**In scope** (plan row `VS-022 | Mixed cart | VS-013`; SRS BR-020–026, §7.1, §7.2,
INV-08, INV-09; FR-05; F-040, F-041; `api-endpoints.md` §10.1 and §29.4):

- One persistent cart per verified customer, mixing physical and STL lines (BR-020,
  BR-021).
- At most one line per product. Adding an existing product merges the quantities
  (BR-022), under a per-cart lock, and the DB `UNIQUE (cart_id, product_id)` is the
  backstop.
- STL lines are always quantity 1 (BR-023). The application enforces it, and so does a
  DB CHECK on a type snapshot (§4).
- Physical quantity is at most `products.max_quantity_per_line` (BR-024), checked again
  after merging.
- A price snapshot is taken when a line is first added (BR-026). `CartRead` shows the
  snapshot price, the current price and `price_changed`.
- Refused on add: unknown, soft-deleted, hidden, inactive-category, unavailable or
  WhatsApp-only products (BR-003, BR-009, §6.5, ADR-022).
- Lines whose product changes after they were added stay in the cart and are flagged in
  `CartRead` (§2, Q6).
- Unverified users may read their (empty) cart but cannot write to it (§14.2).
- The cart read/lock interface that VS-023's checkout consumes (§3.6).
- One new Catalog read port (`CartProductReader`), shared with VS-023's revalidation.

**Non-goals, and which slice owns each:**

| Left out | Owner | Why |
|---|---|---|
| `409 PRODUCT_ALREADY_OWNED` on add | VS-023 | Ownership lives on `order_items`, which VS-023 creates. Until then no STL can be owned (plan row VS-022 "Logic"; VS-023 "Logic") |
| `POST /checkout`, idempotency, `CART_EMPTY`, `CART_PRICE_CHANGED`, `accepted_price_changes`, totals, clearing the cart at checkout | VS-023 | VS-022 supplies `lock_cart_for_checkout` and `clear_cart` (§3.6) |
| Silently dropping an STL acquired since it was added (SRS §7.3 step 5) | VS-023 | Same ownership dependency |
| `422 INVALID_FULFILLMENT` for carts with physical lines | VS-023 (until VS-028) | Checkout behaviour |
| Fulfillment method, address, contact phone, cash rules under the cart lock, dispatch estimate (quantity × batch size) | VS-028 | VS-022 snapshots neither lead time nor batch size, because checkout reads them fresh |
| Payment retry, reconciliation, stale-checkout release | VS-024 | None of them reads or restores a cart. The cart is cleared when the order is created, and a retry acts on the order |
| Locking the customer's cart in a cancel that may insert a cash block | VS-029 / VS-031 | They call `CartStore.lock` from §3.6 after the `orders` locks (ADR-024 decision 9) |
| Cart in the data export, and clearing the cart on anonymisation | VS-044 / VS-045 | Out of this slice |
| Server-computed cart totals | VS-023 | "No client-authoritative total is trusted for checkout" (api §30 `CartRead`). The cart page sums lines for display only |
| Abandoned-cart recovery | Post-V1 | SRS "Near term" list |
| Variants and stock | Never | BR-005 and BR-010: no stock, no selectable variants. The real model has only `price_cents`, `is_available` and `max_quantity_per_line` |

## 2. API and jobs

All routes sit at the version root (`/api/v1/cart`, api-endpoints §10.1), not under
`/me`. The router lives in `app/ordering/api/cart.py` and is mounted in
`app/api/v1/router.py`.

| Method + path | Auth | Request | Success | Errors | Notes |
|---|---|---|---|---|---|
| `GET /api/v1/cart` | `current_user` | — | `200 CartRead` | 401 | No cart row yet: an empty cart with `id: null`. Nothing is written (Q10) |
| `POST /api/v1/cart/items` | `current_verified_user` + CSRF + rate limit | `CartItemAdd` | `200 CartRead` | 401, 403, 422 `PRODUCT_NOT_PURCHASABLE` / `QUANTITY_EXCEEDS_LIMIT` / `CART_LINE_LIMIT_REACHED` / `VALIDATION_ERROR`, 429 | Merges into an existing line. Creates the cart on first write. VS-023 adds 409 `PRODUCT_ALREADY_OWNED` |
| `PATCH /api/v1/cart/items/{product_id}` | same | `CartItemQuantityUpdate` | `200 CartRead` | 401, 403, 404, 422, 429 | Sets an absolute quantity. STL accepts only 1. Refused on a line that is no longer purchasable (Q6) |
| `DELETE /api/v1/cart/items/{product_id}` | same | — | `204` | 401, 403, 404, 429 | Hard-deletes the line (Q1). `404` when the line is absent, per api §10.1 (unlike the idempotent wishlist `DELETE`) |

No jobs. Nothing in this slice runs after commit, so there is no outbox, notification
or audit row: customer self-service on their own data, the same reasoning as ADR-027
decision 8.

### Request schemas (`app/ordering/api/cart_schemas.py`, `extra="forbid"`)

- `CartItemAdd { product_id: UUID, quantity: StrictInt = 1 }`, with
  `1 ≤ quantity ≤ 2_147_483_647` (INTEGER max). The schema rejects 0 and negatives with
  `422 VALIDATION_ERROR`. The upper bound only stops an int4 overflow from becoming a
  500; the real cap comes from the product.
- `CartItemQuantityUpdate { quantity: StrictInt }`, same bounds. Setting 0 is a 422:
  use `DELETE`.

### Response schemas

```text
CartRead
  id: UUID | null                      # null until the first write (Q10)
  items: CartLineRead[]                # ordered (created_at, id) ascending - stable
  contains_physical: bool              # api §30 "derived"
  contains_digital: bool
  updated_at: datetime | null

CartLineRead
  product_id: UUID
  product_type: "physical" | "stl"     # the line's snapshot (§4)
  name: str                            # always present, even when no longer listed
  slug: str | null                     # null when not listed (no link to a 404)
  cover_image: PublicImage | null      # null when not listed or no cover (Q11)
  quantity: int
  snapshot_price: PriceRead            # {amount_cents, currency} - ADR-008
  current_price: PriceRead | null      # null when not listed
  price_changed: bool                  # listed AND current != snapshot (either direction)
  max_quantity: int | null             # current physical cap; null for STL or not listed
  over_cap: bool                       # quantity > product's CURRENT cap; checkout refuses
  purchasable: bool
  unpurchasable_reason: "not_listed" | "unavailable" | "whatsapp_only" | null
```

- **`not_listed`** covers unknown, soft-deleted, hidden (`is_visible = false`) and
  inactive or archived category products. These are exactly the products the storefront
  answers `404` for (`docs/storefront-catalogue.md`). Merging them into one reason leaks
  nothing about why a product vanished.
- **The wishlist precedent** (VS-038 §10 Q6) applies. A line is the owner's own data,
  so the name survives, and the slug, current price and image do not.
- **`purchasable`** is the same predicate as ADR-022's `can_add_to_cart` plus "listed",
  computed by one Catalog domain function (§3.1). By ADR-022 the cart may be stricter
  than the flag, never looser.
- **`over_cap`** is true when the product row exists and `quantity > cap_for(product)`,
  using the product's *current* `max_quantity_per_line` (1 for STL). This happens when
  an administrator lowers the cap after the line was added. The line stays, and `PATCH`
  can lower it.
  - **Checkout (VS-023) must refuse any `over_cap` line** with `422
    QUANTITY_EXCEEDS_LIMIT` (SRS §7.3 step 6), and it re-checks against the cap it reads
    itself, never this flag.
  - `over_cap` is independent of `purchasable`. A hidden line can be both, and its
    `max_quantity` is still null so that the cap of a hidden product is not exposed.

### Error mapping (RFC 9457 `ApiError`, as elsewhere)

| Condition | Status / code | Extension members |
|---|---|---|
| Product not listed (unknown, deleted, hidden, category off), unavailable, or WhatsApp-only, on `POST` | 422 `PRODUCT_NOT_PURCHASABLE` | `reason` (`not_listed` / `unavailable` / `whatsapp_only`). A hidden product and a random UUID give byte-identical bodies (Q12) |
| Same, on `PATCH` of an existing line | 422 `PRODUCT_NOT_PURCHASABLE` | `reason` |
| STL quantity ≠ 1 (`POST` or `PATCH`) | 422 `QUANTITY_EXCEEDS_LIMIT` | `max_quantity: 1`, `requested` |
| Physical quantity after merge (or absolute `PATCH`) > cap | 422 `QUANTITY_EXCEEDS_LIMIT` | `max_quantity`, `requested`, `current_quantity` |
| New line when the cart already has 50 lines | 422 `CART_LINE_LIMIT_REACHED` (new code, §7) | `limit: 50` |
| `PATCH`/`DELETE` on a product not in the cart | 404 `NOT_FOUND` | — |
| Unverified | 403 `EMAIL_VERIFICATION_REQUIRED` | — |
| CSRF | 403 `CSRF_INVALID` | — |
| Rate limit | 429 `RATE_LIMITED` + `Retry-After` | — |

**STL re-add (Q4).** Re-adding an STL that is already in the cart, with quantity 1 or
omitted, is a no-op `200`, because the line is already exactly what was asked. Sending
`quantity: 2` for an STL is `422 QUANTITY_EXCEEDS_LIMIT` (api §29.4 "server requires
exactly 1"; FR-05 "STL quantity greater than one is invalid"). The §10.1 note "STL
quantity forced to 1" is reworded to match in the docs step.

## 3. Layers, function by function

### 3.1 Catalog additions (a new published read; no new Catalog write)

**`app/catalog/domain/storefront.py`** (extended; pure):

```python
class PurchaseRefusal(StrEnum):
    NOT_LISTED = "not_listed"
    UNAVAILABLE = "unavailable"
    WHATSAPP_ONLY = "whatsapp_only"


@dataclass(frozen=True)
class CartProduct:
    """What a cart line needs from Catalog, read in one batched query."""

    id: UUID
    type: ProductType
    name: str
    slug: str
    price_cents: int
    currency: str
    purchase_mode: PurchaseMode | None
    is_available: bool
    max_quantity_per_line: int | None
    listed: bool  # live AND is_visible AND category live and active
    cover: ProductImage | None


def purchase_refusal(p: CartProduct) -> PurchaseRefusal | None:
    """None iff the product can go in a cart now; built on `capabilities()` (ADR-022)."""
```

The order of reasons is `not_listed`, then `unavailable`, then `whatsapp_only`. A
hidden and WhatsApp-only product reports `not_listed`, so it never reveals more than a
404 would.

**`app/catalog/application/ports.py`** (extended; `CartProduct` and `PurchaseRefusal`
re-exported, as VS-038 re-exported `Product`):

```python
class CartProductReader(Protocol):
    async def get_many(self, product_ids: Sequence[UUID]) -> dict[UUID, CartProduct]:
        """One query; unknown ids are simply absent. No visibility filter: `listed` says it."""
        ...
```

**`app/catalog/infrastructure/visibility.py`** (new; one shared function, no copy):

```python
def listed_predicate() -> ColumnElement[bool]:
    """SRS 6.5 storefront visibility; needs `categories` joined. The one definition,
    used by the storefront (VS-015) and by the cart reader (VS-022)."""
    return and_(
        ProductModel.deleted_at.is_(None),
        ProductModel.is_visible.expression,
        CategoryModel.deleted_at.is_(None),
        CategoryModel.is_active.expression,
    )
```

- **Moved, not copied.** These four terms are exactly today's private `_VISIBLE` tuple
  (`storefront_query.py:57-62`). The tuple is deleted, and `_base()`
  (`storefront_query.py:67-75`) calls `.where(listed_predicate())` instead.
- **The storefront's behaviour does not change.** The expressions stay bare
  `is_visible` and `is_active` (the file's own comment at `:56` explains why), so the
  partial indexes still match.
- **Prove it with `EXPLAIN`.** Run it once on `GET /products` before and after the
  change, and note it in the PR. The existing VS-015 and VS-016 integration and smoke
  suites are the regression guard.

**`app/catalog/infrastructure/cart_product_reader.py`** (new):
- `SqlCartProductReader.get_many` runs one `SELECT` over `products` joined to
  `categories`, with a `LEFT JOIN` to the live cover image in `product_images`.
- It selects `listed_predicate().label("listed")` as a column, without filtering, so a
  not-listed line still gets its name. It filters on `WHERE products.id = ANY(:ids)`.
- An empty id list returns `{}` without a query.

**One owner per half of the decision:**
- *Is it listed?* → `listed_predicate()` (SQL, Catalog infrastructure).
- *Given listed, can it be bought now?* → `purchase_refusal()`, which calls the
  existing `capabilities()` (`storefront.py:142-151`).

The cart, VS-023's checkout and the storefront all reach these two functions, never a
re-statement of them. A unit test asserts that `purchase_refusal` agrees with
`capabilities()`, and an integration test (§6) asserts that the storefront and the
cart reader agree on `listed` for every hidden, deleted and category-off case.

**`app/catalog/public.py`** (extended): add `cart_product_reader(session =
Depends(get_session)) -> CartProductReader`, the same shape as `product_store`.

Ordering never imports `app.catalog.infrastructure`. That is enforced by
`test_no_context_imports_another_contexts_infrastructure` and
`test_cross_context_imports_go_only_through_public_or_ports`.

### 3.2 `app.ordering.domain` (pure; imports only `app.catalog.application.ports` types)

**`entities.py`:**

```python
MAX_CART_LINES = 50


@dataclass(frozen=True)
class Cart:
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CartLine:
    id: UUID
    cart_id: UUID
    product_id: UUID
    product_type: ProductType
    quantity: int
    price_snapshot_cents: int
    currency: str
    created_at: datetime
    updated_at: datetime
```

**`cart_rules.py`** (all pure, all unit-tested):

- `cap_for(product: CartProduct) -> int`:
  - STL → `1`.
  - Physical → `max_quantity_per_line`.
  - A physical product with a NULL cap → raise `ProductNotPurchasableError(NOT_LISTED)`
    (fail closed). This is unreachable today because `ck_products_type_integrity` makes
    the cap `NOT NULL` on physical rows, but the domain must not invent a cap.
- `quantity_after_add(product, requested: int, existing: CartLine | None) -> int`:
  1. Raise `ProductNotPurchasableError(product.id, reason)` if
     `purchase_refusal(product)` is not None.
  2. STL: `requested != 1` raises `QuantityExceedsLimitError(max=1)`. Otherwise return
     `1`, including when a line already exists (Q4: idempotent).
  3. Physical: `merged = (existing.quantity if existing else 0) + requested`. If
     `merged > cap_for(product)`, raise `QuantityExceedsLimitError(max=cap,
     requested=requested, current=existing.quantity or 0)`. Never clamp (Q5).
- `check_set_quantity(product, quantity) -> None`: the same refusal check, then
  `quantity > cap_for(product)` raises `QuantityExceedsLimitError`.
- `check_line_capacity(line_count: int) -> None`: raises `CartLineLimitReachedError`
  when `line_count >= MAX_CART_LINES`. It is called only when a *new* line would be
  inserted, so merging into an existing line at 50 lines still works.
- `view_line(line: CartLine, product: CartProduct | None) -> CartLineView`: the pure
  projection behind `CartLineRead`.
  - `product is None` (unknown id) is treated as not listed.
  - `price_changed = listed and product.price_cents != line.price_snapshot_cents`.
  - `over_cap = product is not None and line.quantity > cap_for(product)`. If
    `cap_for` refuses (a physical product with a NULL cap), the line is not purchasable
    and `over_cap` is False.
  - The physical cap is read **live**, never snapshotted. Snapshotting it would let a
    lowered cap be bypassed (BR-024 says "the product's maximum").

**`exceptions.py`:** `ProductNotPurchasableError(product_id, reason)`,
`QuantityExceedsLimitError(product_id, max_quantity, requested, current_quantity)`,
`CartLineLimitReachedError(limit)` and `CartLineNotFoundError(product_id)`. Each is a
domain exception that the API maps (VS-033 and VS-038 pattern).

### 3.3 `app.ordering.application.ports`

```python
class CartStore(Protocol):
    async def lock(self, user_id: UUID, *, create: bool) -> Cart | None:
        """Row-lock the user's cart (`FOR UPDATE`), creating it first if `create`;
        None only when `create` is False and no cart exists."""
        ...

    async def get(self, user_id: UUID) -> Cart | None: ...  # no lock
    async def lines(self, cart_id: UUID) -> list[CartLine]: ...  # (created_at, id)
    async def line(self, cart_id: UUID, product_id: UUID) -> CartLine | None: ...
    async def count_lines(self, cart_id: UUID) -> int: ...
    async def insert_line(
        self,
        *,
        cart_id: UUID,
        product_id: UUID,
        product_type: ProductType,
        quantity: int,
        price_snapshot_cents: int,
        currency: str,
    ) -> CartLine: ...
    async def set_quantity(self, line_id: UUID, quantity: int) -> CartLine: ...
    async def delete_line(self, cart_id: UUID, product_id: UUID) -> bool: ...
    async def clear(self, cart_id: UUID) -> int: ...
    async def touch(self, cart_id: UUID) -> None: ...  # updated_at = now()
```

**Invariant:** every method that writes `cart_items` is called only while the caller
holds `lock(...)` on that cart in the same transaction. Each mutating service below
does so first. It is the serialisation point for merges, the cap and the line count.

### 3.4 `app.ordering.application.services.cart` (new)

Each function takes the stores, runs in the caller's request-scoped session, and does
not commit. `get_session` commits before the response is sent (BUG-46).

- **`add_item(carts, products, *, user_id, product_id, quantity) -> None`**
  1. `cart = await carts.lock(user_id, create=True)`. **The cart lock comes first,
     before any read.**
  2. `product = (await products.get_many([product_id])).get(product_id)`. `None` raises
     `ProductNotPurchasableError(NOT_LISTED)`.
  3. `existing = await carts.line(cart.id, product_id)`.
  4. `new_qty = quantity_after_add(product, quantity, existing)`.
  5. *(VS-023 inserts the STL ownership check here, between 4 and 6, and raises
     `ProductAlreadyOwnedError` → 409.)*
  6. If `existing`:
     - if `new_qty != existing.quantity`, `set_quantity`;
     - the snapshot is kept (Q3).

     Otherwise:
     - `check_line_capacity(await carts.count_lines(cart.id))`;
     - `insert_line(..., product_type=product.type,
       price_snapshot_cents=product.price_cents, currency=product.currency)`.
  7. `await carts.touch(cart.id)` when anything changed.
- **`set_item_quantity(carts, products, *, user_id, product_id, quantity) -> None`**
  - `cart = await carts.lock(user_id, create=False)`.
  - No cart, or no line, raises `CartLineNotFoundError` (404).
  - Read the product; `check_set_quantity`; then `set_quantity`. The snapshot is
    unchanged (Q3), and so is `touch`.
- **`remove_item(carts, *, user_id, product_id) -> None`**
  - `lock(create=False)`, then `delete_line`.
  - `False`, or no cart, raises `CartLineNotFoundError` (404). Otherwise `touch`.
  - No product read: a line for a product that has gone non-public can always be
    removed.
- **`read_cart(carts, products, *, user_id) -> CartView`**
  - `get` (no lock), `lines`, one `products.get_many(ids)`, then `view_line` per line.
  - Three queries in all: no N+1, and no lock on a read.

### 3.5 `app.ordering.infrastructure`

**`models.py`:** `CartModel` and `CartItemModel`, as in §4. `product_type` reuses the
existing PG enum `product_type` with `create_type=False`. Import the enum through
`app.catalog.application.ports.ProductType`.

**`carts.py`** has `SqlCartStore`. Its `lock(user_id, create)` works like this:

```sql
-- create=True only. ON CONFLICT makes concurrent first adds all succeed.
INSERT INTO carts (user_id) VALUES (:uid) ON CONFLICT (user_id) DO NOTHING;
SELECT id, user_id, created_at, updated_at FROM carts
 WHERE user_id = :uid FOR UPDATE;
```

**Isolation level: READ COMMITTED, PostgreSQL's default.**
- The app never overrides it:
  - `make_engine` (`src/app/core/database.py:20-30`) passes no `isolation_level`;
  - `make_session_factory` (`:34-35`) sets none;
  - nothing in `src/`, `migrations/`, `tests/conftest.py` or `docker-compose.yml` sets
    `default_transaction_isolation`.
- The postgres:16 image keeps the server default.
- If a future change raises the level to REPEATABLE READ or SERIALIZABLE, step 5 below
  raises a serialisation error instead of reading A's row, and this design must be
  revisited.

**How two concurrent first adds (A and B, the same user, no cart yet) both succeed
under READ COMMITTED:**
1. A inserts the row, which is uncommitted.
2. B's `INSERT` hits the unique index on `user_id` and **waits** for A's transaction.
3. A takes `FOR UPDATE`, adds its line and commits.
4. B's `INSERT` resolves to `DO NOTHING`, which is not an error and returns no row.
5. B's `SELECT … FOR UPDATE` sees A's committed row, locks it, and B adds its line.

The result is one cart and two lines. If A rolls back instead, B's `INSERT` proceeds
and B creates the cart. **No path raises `UniqueViolation`, and no retry loop is
needed.** `create=False` (`PATCH`, `DELETE`, checkout) skips the INSERT and returns None
when no row exists.

- **`FOR UPDATE`, as the review asked.** Only the lock holder writes `cart_items`, and
  each such insert's FK check needs `KEY SHARE` on `carts`, which its own transaction
  already exceeds. So the stronger mode blocks no other transaction's work. It also
  matches the "lock the cart" wording of SRS §7.3 and ADR-024 literally.
- **`insert_line`** is a plain `INSERT … RETURNING`. Under the lock no conflict is
  expected. If `UNIQUE (cart_id, product_id)` still fires, that is a bug, and it
  surfaces as a 500 `IntegrityError` the concurrency test would catch. No `ON CONFLICT`
  path hides it.
- **The other methods** are single statements:
  - `set_quantity` also sets `updated_at = now()`;
  - `delete_line` is `DELETE … RETURNING id`;
  - `clear` is `DELETE FROM cart_items WHERE cart_id = :id`, returning the rowcount.

### 3.6 Interface VS-023 checkout consumes (published in `app.ordering.application.services.cart`)

Checkout is in the same bounded context (Ordering), so it calls the application
service directly. No `public.py` export is needed until another context needs the cart.

```python
@dataclass(frozen=True)
class LockedCart:
    cart: Cart
    lines: tuple[CartLine, ...]  # (created_at, id) ascending


async def lock_cart_for_checkout(carts: CartStore, *, user_id: UUID) -> LockedCart | None:
    """Lock the cart and load its lines. None means no cart (VS-023: 409 CART_EMPTY);
    an empty `lines` is also CART_EMPTY. Never creates a cart."""


async def clear_cart(carts: CartStore, locked: LockedCart) -> None:
    """Delete every line of a cart the caller still holds locked (SRS §7.3 step 12)."""
```

Checkout revalidates with the same `CartProductReader.get_many` and
`app.catalog.application.ports.purchase_refusal` (SRS §7.3 steps 4 and 6), including
refusing every `over_cap` line by its own cap read.

**Requirement on VS-023: no silent drops.**
- **Lines that cannot be bought are refused, never dropped.** If any line is
  `not_listed`, `unavailable` or `whatsapp_only`, or is over the product's current cap,
  checkout writes nothing and answers 422. It answers `PRODUCT_NOT_PURCHASABLE`, or
  `QUANTITY_EXCEEDS_LIMIT` when only caps fail.
  - The body lists **every** offending line: `{product_id, reason}`, where `reason` is
    `not_listed`, `unavailable`, `whatsapp_only` or `over_cap`, and over-cap entries
    also carry `max_quantity`.
  - The cart is left intact (entities rule: "a failed checkout leaves the Cart
    unchanged").
- **The one exception (SRS §7.3 step 5, `SRS.md:658`):** an STL that became owned
  since it was added is dropped from the order, not refused.
  - The checkout response must name each dropped product id (for example
    `dropped_lines: [{product_id, reason: "already_owned"}]`), so the customer is told.
  - If dropping leaves no lines, the answer is `409 CART_EMPTY`.
  - An ownership-index violation during the insert (the STL is held by another live
    order) stays `409 PRODUCT_ALREADY_OWNED`, per the VS-023 plan row and ADR-025.

**The snapshot price is display-only. Checkout charges the live price.**
- `CartLine.price_snapshot_cents` is never an amount anyone is charged, and it never
  feeds a total.
- Checkout must compute every line price and the order total server-side from
  `products.price_cents`, as read by `CartProductReader` inside the checkout
  transaction (SRS §7.3 step 8, "recompute all totals server-side"; api §30 "no
  client-authoritative total").
- The snapshot has one job: comparing it with that live price decides
  `409 CART_PRICE_CHANGED`, unless the client sends the change in
  `accepted_price_changes`.
- `order_items` snapshot the **live** price at order creation, not the cart snapshot.

**Lock order contract** (VS-023, VS-028 and later slices must keep it):

1. *(VS-023)* the idempotency record insert. This is a unique-index wait, not a row
   lock on existing data.
2. `carts` row, `FOR UPDATE` (`lock_cart_for_checkout`). **`cart_items` rows are never
   locked on their own.** The cart row guards them, because every writer holds it
   (§3.3 invariant).
3. Catalog reads, with **no explicit** product row locks (Q9).
4. *(VS-028)* the chosen address `FOR SHARE`, then
   `pg_advisory_xact_lock(phone hash)`.
5. `INSERT` the new `orders`, `order_items` and `payments` rows. **No existing `orders`
   row is locked while the cart lock is held.**
6. `clear_cart`, which runs under the same cart lock.

Cart writes (`add_item`, `set_item_quantity`, `remove_item`) take step 2 only. Their
inserts add implicit FK `KEY SHARE` locks on `carts`, `users` and `products`.

**Compatibility with the existing lock orders** (quoted verbatim):

| Source | Text | Compatible? |
|---|---|---|
| This plan (above) | "`carts` row, `FOR UPDATE` … No existing `orders` row is locked while the cart lock is held." | — |
| ADR-024 decision 9 (`docs/adr/ADR-024-…md:26`) | "**Lock order: `orders` before `order_items`, everywhere.** Every write that changes an order's lines, payment or refunds locks the `orders` row first (`FOR UPDATE`)" | **Yes.** Cart code changes no existing order. Checkout only INSERTs new orders, after the cart lock |
| ADR-024 table, "Cash checkout" (`:39`) | "cart → phone advisory lock → INSERT order (no existing `orders` row is locked)" | **Yes, identical.** Steps 2, 4 and 5 above, with VS-028's address `FOR SHARE` before the advisory lock |
| ADR-024 table, "Customer self-cancel, admin cancel" (`:31`) | "`orders` → all physical lines by `id` → `payments` → INSERT refund rows → (if a block may be inserted) the customer's cart → phone advisory lock → recompute" | **Yes.** That path waits for a cart only while holding `orders`. Checkout holds a cart and never waits for an existing `orders` row, so no cycle closes. Both take the cart *before* the advisory lock |
| VS-004 (`docs/vertical-slice-plan.md:124`, `:129`) | "1. Lock the token, then lock the user." … "Lock order is `users` before `sessions` everywhere." | **Yes.** Cart code locks neither `users` nor `sessions` nor tokens explicitly |
| ADR-018 (`docs/adr/ADR-018-authentication-epoch.md:56`) | "the lock order is **`users` before `sessions`, everywhere**" | **Yes**, as above |
| ADR-027 decision 4 | "`SELECT … FROM users WHERE id = :uid FOR NO KEY UPDATE`" for address writes | **Yes.** See below |

**The implicit FK locks**, checked one by one:
- **`users`:** the `carts` insert's FK check takes `KEY SHARE` on `users`.
  - That waits only while an Identity transaction holds `users FOR UPDATE` (login,
    password reset: ADR-018 `:60-62`).
  - The address book's `FOR NO KEY UPDATE` does not conflict with `KEY SHARE`, so it
    never makes the cart wait.
  - Identity and address transactions never touch `carts`, so they never wait on the
    cart. No cycle.
- **`products`:** the `cart_items` insert's FK check takes `KEY SHARE` on `products`.
  - That conflicts only with `ProductRepository.get_for_update`'s `FOR UPDATE`
    (`product_repository.py:121-129`, used by image changes).
  - Those transactions never touch carts, and ordinary product `PATCH`es take
    `FOR NO KEY UPDATE` (they change no key column), which does not conflict.
  - So the cart only ever *waits*, briefly, and is never waited on. No cycle.
- **Cancel-with-block versus the cart:** the cart side holds the cart lock and waits on
  nothing the cancel holds (`orders`, `payments`). The cancel waits on the cart.

**Verdict: compatible.** VS-029 and VS-031 must call `CartStore.lock(..., create=True)`
only after their `orders` locks, as ADR-024 already says. ADR-029 restates this
contract.

### 3.7 `app.ordering.api`

**`cart.py`** has one router, `prefix="/cart"`, `tags=["cart"]`:
- **Dependencies:**
  - `current_user`, `current_verified_user`, `require_csrf` and `not_found_error` come
    from `app.identity.public`;
  - `cart_product_reader` comes from `app.catalog.public`.
  - The task brief says `current_verified_customer`, but the dependency in the code is
    `current_verified_user`.
- **`_cart_rate_limit`** works exactly like `_wishlist_rate_limit`:
  - it depends on `current_verified_user`, so an anonymous or unverified caller never
    consumes the budget;
  - the call is `enforce_rate_limit(key_prefix="cart", subject=str(user.id),
    limit=300, window_seconds=3600)` (Q8);
  - it is mounted with `require_csrf` on `POST`, `PATCH` and `DELETE`.
- **Every write route** calls the service and then re-reads the cart with `read_cart`
  for the `200 CartRead` body. `DELETE` returns `204`.
- **Exception mapping** follows §2, in the same style as `addresses.py`'s
  `ADDRESS_LIMIT_REACHED`.

**`cart_schemas.py`** holds the schemas in §2. It reuses `PriceRead` and `PublicImage`
from Catalog's API schemas only if they are re-exported through `catalog.public`.
Otherwise it defines identical local models, because the architecture test forbids
`app.catalog.api` imports. The decision is made at implementation time; the
architecture test is the arbiter.

**Mounting:** `router.include_router(cart_router)` in `app/api/v1/router.py`, with a
one-line comment matching that file's style (`# VS-022. The cart: /api/v1/cart …`).

## 4. Database

**Migration** `<rev>_carts_and_cart_items.py`, `down_revision = "75ad58ebd9e5"`. It
only adds objects, so it is backward-compatible: no existing column changes, and old
code ignores the new tables. It is reversible.

**`carts`** (database-design §8.1):

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | UUID | No | PK, `gen_random_uuid()` (ADR-002) |
| `user_id` | UUID | No | FK → `users.id` **ON DELETE CASCADE**. `UNIQUE` (`uq_carts_user_id`) |
| `created_at` | TIMESTAMPTZ | No | `now()` |
| `updated_at` | TIMESTAMPTZ | No | `now()`, app-maintained |

CASCADE is required, not optional: `test_no_foreign_key_to_users_can_block_the_purge`
asserts that every FK to `users` is `c` or `n`, and database-design §19 says "CASCADE
only on safe purge". Only never-verified accounts are deleted, and they cannot write a
cart. A cart has no `deleted_at`: it is retained and emptied, never removed
(entities doc; the retention table says "mutable operational data").

**`cart_items`** (database-design §8.2, plus `product_type`):

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `cart_id` | UUID | No | FK → `carts.id` ON DELETE CASCADE |
| `product_id` | UUID | No | Part of a composite FK, see below |
| `product_type` | `product_type` (existing enum) | No | Snapshot; type is immutable (VS-013) |
| `quantity` | INTEGER | No | `CHECK (quantity > 0)` |
| `price_snapshot_cents` | BIGINT | No | `CHECK (price_snapshot_cents >= 0)` (ADR-008) |
| `currency` | CHAR(3) | No | default `'USD'`, `CHECK (currency = 'USD')` |
| `created_at`, `updated_at` | TIMESTAMPTZ | No | `now()` |

**Constraints and indexes:**

- `uq_cart_items_cart_product UNIQUE (cart_id, product_id)`. This is the INV-09
  guarantee (SRS §21.2). It is a plain unique, not a partial one, because lines are
  hard-deleted (Q1). Its index also serves `lines(cart_id)` and `line(cart_id,
  product_id)`.
- `ck_cart_items_stl_quantity_one CHECK (product_type <> 'stl' OR quantity = 1)`. This
  is INV-08 and SRS §21.2 "STL line quantity = 1", enforced by the DB. database-design
  §8.2 notes that this needs the type snapshotted onto the line, and calls the
  duplication "not required by the SRS". The slice plan row asks for it, so this plan
  adopts it (Q2).
- `fk_cart_items_product_type FOREIGN KEY (product_id, product_type) REFERENCES
  products (id, type) ON DELETE RESTRICT ON UPDATE RESTRICT`. This needs a new
  `uq_products_id_type UNIQUE (id, type)` on `products`.
  - It is additive and cannot fail on existing data, because `id` is already unique.
    Products are few, so the index build is instant.
  - It makes the snapshot provably equal to the real type, and it makes the DB refuse
    any `UPDATE products SET type` while a cart line references the product. Type
    immutability was only domain-enforced before.
  - **Every write path of `products.type`, checked on `main`:**
    - INSERT only: `ProductRepository.add` (`product_repository.py:87`, through the
      admin create command and `scripts/dev_seed.py:360`).
    - The sole UPDATE, `save_if_version` (`:100-117`), writes
      `_columns(product.attributes)`, and `ProductAttributes` has no `type`
      (`product.py:51`).
    - `AdminProductUpdate` refuses `type` (`product_schemas.py:133-134`,
      `extra="forbid"`).
    - No migration updates it.
  - **`type` never changes today.** Should a future path change it, `ON UPDATE
    RESTRICT` **blocks** the update (`23503`) while any cart line references the
    product. It never cascades, so `cart_items.product_type` is never rewritten, and
    `ck_cart_items_stl_quantity_one` cannot be violated by a product update.
  - With `ON UPDATE CASCADE` instead, converting a physical product to STL would
    rewrite every cart line's type, and any line with quantity > 1 would fail the CHECK
    and abort the admin's update. That is why CASCADE is rejected.
  - **Decision: keep the FK** (Q2), on that evidence.
  - **Two layers (verified in step 6):** a bare `SET type = 'stl'` is stopped first by
    `ck_products_type_integrity` (23514), because CHECKs fire before the RI trigger. The
    composite FK is the backstop for a change that is otherwise a valid STL row (23503,
    `fk_cart_items_product_type`). With the FK dropped, that row change succeeds.
  - VS-023's `order_items.product_type`, on which the ownership index depends, can
    reuse the same unique key.
  - If the owner rejects Q2, drop the composite FK and keep the plain
    `product_id → products.id RESTRICT` FK plus the CHECK.
- No `cart_items(product_id)` index. Products are never hard-deleted, so the RESTRICT
  check never runs. No query in V1 reads "which carts hold product X". Add it only if a
  later slice needs that query.
- No line-count constraint in the DB. The count is checked under the cart lock (§3.4),
  as ADR-027 does for the 20-address cap.

**Downgrade:** drop `cart_items`, then `carts`, then `uq_products_id_type`, in reverse
order. The `product_type` enum is not dropped, because `products` owns it.

**Migration test seed:** add one `carts` row (no lines) for the seeded user to `_SEED`
in `test_deep_db_constraints_and_migrations.py`. Every down/up step then runs with cart
data present, and `downgrade base` proves the cascade-free drop works.

## 5. Performance and abuse

- **Max lines per cart: 50** (Q7). The 51st *new* product is `422
  CART_LINE_LIMIT_REACHED`. This bounds `GET /cart`, the response size, the `IN (...)`
  list, and checkout's line loop. The list is not paginated, like the 20-address list
  (ADR-027 decision 6).
- **Per-line quantity:** the product cap for physical lines, 1 for STL. The schema
  bounds requests at the INTEGER max, so nothing can overflow int4.
- **Rate limits:** one bucket, `key_prefix="cart"`, keyed by user id, **300/hour**,
  shared by `POST`, `PATCH` and `DELETE` (Q8).
  - It is built on `enforce_rate_limit` (`src/app/core/rate_limit.py:19`), the
    subject-agnostic helper, with `subject=str(user.id)` taken from
    `current_verified_user`. This is the same construction as
    `src/app/engagement/api/wishlist.py:94-107`.
  - The IP-keyed factory `rate_limiter` (`rate_limit.py:66`, `subject=client_ip` at
    `:78`) is deliberately not used.
  - It is not IP-keyed, for the shared-NAT reason in VS-038 §5 and VS-020.
  - It fails closed: a Redis outage is `503`, through `DEPENDENCY_UNAVAILABLE_ERRORS`.
  - `GET` is unlimited, like `GET /me/wishlist`.
- **Query count:**
  - `GET` takes 3 statements: cart, lines, and one Catalog batch.
  - `POST` takes about 6 writes and reads under the lock, plus the 3-statement re-read.
  - `IN`/`ANY` with at most 50 ids uses the `products` PK.
- **Lock order:** §3.6.
  - The cart row is the only lock a cart write takes.
  - The lock is held for a few ms: no external call and no outbox inside it.
  - Product rows are never locked by cart code (Q9).
  - One customer's adds serialise per cart. Different customers never contend.
- **Concurrent adds:** serialised by the cart lock, with the merge computed from the
  line as read *under* the lock. The unique index is the backstop if the invariant is
  ever broken.
  - Two `+3` adds against a cap of 5 give one `200` with 3 and one `422`, never a line
    of 6.
  - Two first-adds for a user with no cart give one cart (`ON CONFLICT DO NOTHING` +
    lock).
- **Accepted race (Q9):** an administrator lowers a cap or a price, or hides a product,
  between the cart's Catalog read and the commit. The line can then briefly exceed the
  new cap, or carry the old price. `CartRead` flags it at once (`over_cap`,
  `price_changed`, `purchasable`). Checkout revalidates everything under its own lock
  (SRS §7.3 steps 4–6, and the entities rule "Cart contents never prove that a Product
  remains purchasable"). Nothing is ever *bought* past the cap.
- **Enumeration:** `POST` with an unknown, deleted, hidden or inactive-category id
  answers one identical `422 PRODUCT_NOT_PURCHASABLE {reason: "not_listed"}`. It is no
  better an oracle than the public `GET /products/{slug}` 404.

## 6. Tests

All new test files live under the existing folders. Postgres and Redis are real
testcontainers (CLAUDE.md: no mocked DB for constraints).

**Unit** (`tests/unit/ordering/`, `tests/unit/catalog/`):

- **`purchase_refusal`:**
  - A table test over `type × purchase_mode × is_available × listed`.
  - A property test that `purchase_refusal(p) is None` ⇔ `listed and
    capabilities(...).can_add_to_cart`. This pins ADR-022's "never looser than the
    flag".
  - Reason order: hidden + WhatsApp-only gives `not_listed`, and hidden + unavailable
    gives `not_listed`.
- **`cap_for`:**
  - STL → 1.
  - Physical → its cap.
  - Physical with a NULL cap → `ProductNotPurchasableError` (the defensive branch).
- **`quantity_after_add`:**
  - STL `1` → 1, and STL `2` → `QuantityExceedsLimitError(max=1)`.
  - STL re-add when a line exists → 1 (no error).
  - Physical first add: at the cap is OK, and cap + 1 is refused.
  - Physical merge `existing 2 + 3` with cap 5 → 5, and with cap 4 → refused, carrying
    `current_quantity=2`.
  - A refused product (each reason) is refused before any quantity check.
- **`check_set_quantity`:**
  - Physical at the cap is OK, and cap + 1 is refused.
  - STL to 1 is OK, and STL to 2 is refused.
  - Each refusal reason is refused.
- **`check_line_capacity`:** 49 is OK, and 50 raises.
- **`view_line`:**
  - `price_changed` is true for a rise and for a fall, and false when equal.
  - Not listed → `current_price` None and `price_changed` false; the slug is hidden but
    the name is kept.
  - A cap lowered below the quantity → `over_cap` is true. A hidden product whose cap
    was lowered → `over_cap` is true and `max_quantity` is null.
  - Quantity exactly at the cap → `over_cap` is false. An STL line → `over_cap` is
    always false.
  - An unknown product (None) → not listed.
- **Services against fakes** (a fake `CartStore` records call order, plus a fake
  `CartProductReader`):
  - `lock` is the **first** call in `add_item`, `set_item_quantity` and `remove_item`.
  - The snapshot is the current price on insert and unchanged on merge and on `PATCH`.
  - `count_lines` is not consulted when merging.
  - A no-op STL re-add writes nothing and does not `touch`.
  - `remove_item` never reads Catalog.
  - `read_cart` makes exactly one `get_many` call.
  - `lock_cart_for_checkout` returns None without a cart and never creates one.
- **Schema:**
  - `quantity` of 0, -1, 2**31, `1.0` or `"1"` → 422 (StrictInt).
  - An unknown field → 422.
- **Architecture:** extend `test_deep_architecture.py`'s published-surface guard set so
  that the scan must see `app.catalog.public` used from `ordering`. Ordering imports
  Catalog only via `public` or `application.ports`.

**Integration** (`tests/integration/ordering/`, real Postgres through the existing
fixtures):

- **API happy path:** add physical, add STL, then `GET` shows both lines, with
  `contains_physical` and `contains_digital` true, snapshot equal to current, and
  `price_changed` false. Then `PATCH` and `DELETE`, and `GET` again.
- **Merge:** adding the same physical product twice gives one line with the summed
  quantity.
- **STL re-add:** returns 200 and one line with quantity 1.
- **Unverified user:** `GET` is 200, empty, `id: null`, and **no `carts` row exists
  afterwards**. `POST`, `PATCH` and `DELETE` are 403 `EMAIL_VERIFICATION_REQUIRED`, and
  the rate-limit bucket is untouched.
- **Anonymous:** 401 on all four routes.
- **CSRF:** a write without the header is 403.
- **Refusals with identical bodies:** an unknown UUID, a soft-deleted product, a
  hidden product and a product in an inactive category each give the **same**
  `422 PRODUCT_NOT_PURCHASABLE` body (byte-compare the bodies).
- **Other refusals:**
  - A WhatsApp-only product → `reason: whatsapp_only`.
  - An unavailable product → `reason: unavailable`.
  - A `both`-mode physical product is accepted.
- **Quantity errors:**
  - STL `quantity: 2` → 422, and `PATCH` of an STL line to 2 → 422.
  - A physical add over the cap → 422 with `max_quantity`, and the cart is unchanged
    (row count and quantity).
- **`PATCH` and `DELETE` on a missing line:**
  - `PATCH` on a product not in the cart → 404.
  - `DELETE` on an absent line → 404.
  - The same two calls when the user has no cart at all → 404, and no cart is created.
- **Product changes after adding** (owner question 6 and the brief's required cases):
  - Price raised → `price_changed: true` with both prices. Price restored →
    `price_changed: false`.
  - Product hidden → the line stays: `purchasable: false`, `not_listed`, name kept, slug
    and `current_price` null.
  - Product soft-deleted → the same as hidden.
  - Its category archived or deactivated → `not_listed`.
  - Switched to `whatsapp_only` → `purchasable: false`, `whatsapp_only`. A `PATCH` on
    that line is 422, and a `DELETE` is 204.
  - Made unavailable → the same as WhatsApp-only, with `unavailable`.
  - Cap lowered below the quantity → `over_cap: true`. `PATCH` down to the
    new cap is 200, and `PATCH` up is 422.
- **Delete and re-add:** after `DELETE`, re-adding at a new price gives a **new**
  snapshot equal to the new price (Q1/Q3).
- **Line limit:** with 50 lines, a 51st distinct product → 422
  `CART_LINE_LIMIT_REACHED`. Adding to an existing line at 50 lines → 200.
- **Rate limit:** the 301st write in the window → 429 with `Retry-After`. `GET` is
  never limited.
- **Ordering and isolation:**
  - Lines come back in add order, and stay stable after a `PATCH`.
  - User B's `GET` never shows user A's lines, and B's `PATCH` on A's product id
    answers 404 (no cross-user line).
- **DB constraints, written straight to Postgres** (not mocked):
  - a second `(cart_id, product_id)` row → `23505`;
  - an STL row with `quantity = 2` → `23514`;
  - `quantity = 0` → `23514`;
  - `price_snapshot_cents = -1` → `23514`;
  - `currency = 'EUR'` → `23514`;
  - a `product_type` that doesn't match the product → `23503` (composite FK);
  - a second cart for one user → `23505`;
  - `UPDATE products SET type = 'stl'` on a referenced physical product → `23503`.
- **Purge:** a never-verified user with a seeded cart and line is purged by the
  existing job, and both rows cascade away.
  `test_no_foreign_key_to_users_can_block_the_purge` stays green.
- **Migrations:** `test_every_migration_step_goes_down_and_up_with_data_present` runs
  with the new seed, and `test_migration_reversibility` is green.
- **One visibility rule** (`tests/integration/catalog/`). For each case below, the
  storefront `GET /products/{slug}` answers 404 **exactly when** `SqlCartProductReader`
  returns `listed=False`:
  - visible;
  - hidden;
  - soft-deleted;
  - category archived;
  - category inactive;
  - unavailable (listed, so 200);
  - WhatsApp-only (listed, so 200).

  A static check asserts that `storefront_query.py` and `cart_product_reader.py` both
  call `listed_predicate()`, and that neither defines `is_visible` or `is_active`
  terms of its own.
- **Live price at checkout:** asserted in VS-023, not here. This slice's test only
  checks that `CartRead` never exposes a total.

**Concurrency** (`tests/concurrency/test_cart_races.py`, `meet_or_fail` barrier):

- **The named test:** two concurrent `POST`s of one physical product, each `+3`, with
  cap 5. The result is exactly one line of quantity 3, one 200 and one 422, and never
  quantity 6 or two lines.
- N concurrent `POST`s of the same physical product, each `+1`, with cap N−1, give a
  final quantity of exactly N−1, and exactly one 422.
- **Two concurrent first adds (Revision 1, point 2):** a verified user with **no
  `carts` row** sends two `POST /cart/items` for two *different* products, released
  together at the barrier.
  - Both answer 200.
  - Exactly one `carts` row exists for the user.
  - Both products are lines of that cart.
  - No `UniqueViolation` or 500 is logged.
  - It runs 20 iterations, to hit both interleavings (the second insert waiting on the
    first; the second arriving after the commit).
  - A variant has the first transaction roll back, by forcing a 422 on its product.
    The second must still create the cart and answer 200.
- N concurrent first adds of the same product (each `+1`, cap ≥ N) for a user with
  **no cart** give exactly one `carts` row and one line of quantity N, with no 500.
- Concurrent `POST`s of the same STL give one line of quantity 1, and all calls 200.
- With 49 lines, two concurrent adds of two different new products give exactly one
  200 and one 422 `CART_LINE_LIMIT_REACHED`.
- Concurrent `PATCH` and `DELETE` of one line give no 500. The end state is either
  "line gone" or "line at the patched quantity", and a later `GET` agrees.
- A concurrent add and an admin price `PATCH` of the same product give a snapshot that
  is either the old or the new price, never a third value, and `price_changed` matches.
- **Lock-removed proof** (ADR-027 precedent): run the first test 15 times with
  `CartStore.lock` patched to a non-locking `SELECT`. At least one run must yield 422 →
  500, or a quantity over the cap. Do this once, record it in the PR description, and
  do not commit it as a test.

**Smoke** (`tests/smoke/test_vs022_smoke.py`, wired into `tests/conftest.py` as
`VS022_SMOKE`, the same way VS-038 was): add physical, add STL, `GET`, `PATCH`,
`DELETE`, `GET`.

**Contract:**
- Regenerate the OpenAPI snapshot (`tests/unit/test_openapi_snapshot.py`) and
  `docs/frontend-handoff/openapi.json`.
- `test_every_observed_status_is_documented_in_openapi` must pass. Every status in §2's
  table is declared in `responses=`.

## 7. Docs and ADRs

- **ADR number:** `docs/adr/` on `main` holds ADR-001 to ADR-028 (the last is
  `ADR-028-keyed-monthly-rotated-ip-hashes.md`), and no remote branch adds a higher
  one. So **029 is the next free number**. Re-check it immediately before writing,
  because a parallel slice could take 029 first.
- **New ADR-029: "Cart: hard-deleted lines, a type snapshot with a composite FK, a
  first-add price snapshot, no product locks, and a 50-line cap".** It records the
  decisions for Q1–Q9 and Q12. An ADR is needed because:
  - Q1 departs from BR-018's blanket soft delete, under the retention table's
    "cleanup allowed";
  - Q2 changes database-design §8.2's "not required" note;
  - §3.6 extends ADR-024 decision 9's lock table.
- **New `docs/cart.md`:** the contract page, like `docs/address-book.md`. It covers
  routes, `CartRead`, the reasons, the errors, the limits and the lock contract.
- **`docs/requirments/api-endpoints.md`:**
  - §5.2: add `422 CART_LINE_LIMIT_REACHED`.
  - §10.1:
    - `POST` gains `CART_LINE_LIMIT_REACHED`;
    - `DELETE` gains 429;
    - "STL quantity forced to 1" becomes "STL accepts only quantity 1; re-adding an STL
      already in the cart is a no-op";
    - `GET` notes `id: null` for an empty, never-written cart.
  - §29.4: the quantity bounds.
  - §30 `CartRead`: the full field list from §2.
- **`docs/requirments/database-design.md`:**
  - §8.2: add `product_type`, the CHECK and the composite FK, and replace the
    "cross-table… not required" paragraph.
  - §6.4: add `uq_products_id_type`.
  - §15.3: add the STL CHECK.
- **`docs/requirments/entities-and-business-rules.md`:** CartItem deletion strategy →
  "hard delete (operational data; ADR-029)".
- **`docs/vertical-slice-plan.md`:**
  - **VS-038 Status line, a one-line fix:** change line 1009 from `**Status:** Not
    started` to `**Status:** Done`. The summary-table row already says Done (since
    `e0892e3`), and only the section line is stale.
  - VS-022: the Status line and the table row both become `Done`, with an "As built"
    block (migration id, ADR-029, `docs/cart.md`).
- **`README.md`:** the slice list, if it tracks per-slice status (VS-038 updated it in
  `e0892e3`).
- **No `docker-compose.yml` change.** No new service, port or env var. The API and
  worker already get the in-network `DATABASE_URL` and `REDIS_URL`, and that stays
  true. If a future change adds a dockerized service, it must get the in-network URLs
  (`postgres:5432`, `redis:6379`), never `localhost`.

## 8. Implementation steps, in order

Branch: `vs-022-mixed-cart` from an up-to-date `main` (CONTRIBUTING).

1. **Catalog domain:** `PurchaseRefusal`, `CartProduct` and `purchase_refusal` in
   `storefront.py`, plus their unit tests, including the property test against
   `capabilities()`.
2. **Catalog port and adapter:**
   - `CartProductReader` in `ports.py`;
   - `SqlCartProductReader` (one query, with the category and cover joins);
   - `cart_product_reader` in `catalog/public.py`;
   - an integration test that asserts one query, and `listed` for each of the hidden,
     deleted and category-off cases.
3. **Ordering domain:** the entities, `cart_rules.py` and the exceptions, with the full
   §6 unit tests.
4. **Ordering ports and services:** `CartStore` and `services/cart.py`, covering
   `add_item`, `set_item_quantity`, `remove_item`, `read_cart`,
   `lock_cart_for_checkout`, `clear_cart` and `LockedCart`. Unit-test them against
   fakes, including the lock-first call order.

   **CHECKPOINT:** confirm owner answers to Q1–Q4 and Q9 before touching the schema.
   They decide the table shape and the lock contract.
5. **Migration:**
   - Announce the migration lock (CONTRIBUTING).
   - Re-derive the single head; it is expected to be `75ad58ebd9e5`.
   - Run `alembic revision`, then hand-write `upgrade` and `downgrade`.
   - Run `alembic heads` (exactly one), `upgrade head`, `downgrade -1` and
     `upgrade head`.
   - Add the `_SEED` cart row.
   - Merge this as its own small PR, then free the lock.
6. **Ordering infrastructure:** `CartModel`, `CartItemModel` and `SqlCartStore`. Write
   the DB-constraint integration tests here.
7. **API:** the schemas and `cart.py` router, the error mapping, `_cart_rate_limit`, and
   mounting in `app/api/v1/router.py`.
8. **API integration tests** (§6).
9. **Concurrency tests** (§6), plus the one-off lock-removed proof.
10. **Smoke test** and its `conftest.py` wiring. Regenerate the OpenAPI snapshot and
    `docs/frontend-handoff/openapi.json`.
11. **Docs:**
    - ADR-029 and `docs/cart.md`;
    - the api-endpoints, database-design and entities edits;
    - **the VS-038 Status-line fix**;
    - the VS-022 Status line, table row and As-built block;
    - the README.
12. **Checks.** Run lint and types first: `ruff check .`, `ruff format --check .` and
    `mypy src tests`. Then run the suite **in sequential chunks**, never as one full
    run:
    1. `pytest tests/unit`
    2. `pytest tests/integration/ordering tests/integration/catalog`
    3. `pytest tests/integration --ignore=tests/integration/ordering --ignore=tests/integration/catalog`
    4. `pytest tests/concurrency`
    5. `pytest -m smoke`
    6. `pytest tests/contract tests/security`

    Each chunk must be green before the next starts. Report any failure verbatim.

## 9. Risks

- **Lock-order drift.** A later slice (VS-029, VS-031) could lock the cart *before* an
  `orders` row, or a checkout could lock an existing order while holding the cart. Both
  create a deadlock cycle. Mitigations:
  - the lock contract in §3.6 and ADR-029;
  - the `CartStore.lock` docstring points to it;
  - VS-029 and VS-031 already list cart-after-orders in ADR-024.
- **A writer bypasses the cart lock.** A future method that writes `cart_items` without
  `lock(...)` would reopen the merge race. The unique index turns that into a 500
  rather than corrupt data. The lock-first unit tests and the concurrency suite are the
  guards.
- **Composite FK on `products`.** It adds a unique index to a Catalog table from an
  Ordering migration, and it blocks `UPDATE products SET type` for products in carts.
  Type is already immutable in the domain, so this only hardens an existing rule. Q2
  can drop it.
- **Hard delete versus BR-018.** A reviewer may read BR-018 as forbidding it. The
  retention table explicitly allows cleanup, ADR-029 records the choice, and no audit
  or history depends on cart lines.
- **The snapshot kept on merge is surprising.** A customer who re-adds after a price
  rise still sees `price_changed: true`. This is intended (Q3): it guarantees the
  explicit confirmation BR-026 asks for, and the UI copy must explain it.
- **ADR-022 divergence.** If Catalog later tightens `capabilities()` but not
  `purchase_refusal`, the cart could become looser than the flag. The property test
  pins them together.
- **Line limit and checkout timing.** 50 lines × Catalog revalidation is one query in
  VS-023. That is fine, but VS-023 must not loop `get_by_id` per line.

## 10. Owner questions (each with a recommendation)

1. **Removing a line: hard delete or soft delete?** *Recommend hard delete* with a
   plain `UNIQUE (cart_id, product_id)`.
   - Cart lines are "mutable operational data; cleanup allowed" (database-design
     retention table), and SRS §21.2 lists a plain "Unique (cart, product)".
   - Nothing reads a removed line.
   - Soft delete would need a partial unique index, `deleted_at` filters everywhere,
     and an ever-growing table, and checkout's "clear the cart" would become an
     `UPDATE` of every line.
   - Record the exception to BR-018 in ADR-029.
2. **Should the STL quantity rule be DB-enforced?** That means a `product_type`
   snapshot, a CHECK, and a composite FK to a new `UNIQUE (products.id, type)`.
   *Recommend yes, all three.* The slice plan row asks for the CHECK, and SRS §21.2
   lists "STL line quantity = 1" as a DB invariant. The composite FK makes the snapshot
   provably correct, and VS-023's `order_items` can reuse it. A fallback is the CHECK
   plus the snapshot with a plain FK.
   - **Evidence (Revision 1):** no write path ever updates `products.type` (§4 lists
     each one, with file:line).
   - `ON UPDATE RESTRICT` blocks any future change rather than cascading, so the CHECK
     can never fail as a side effect.
   - Keeping the FK costs nothing on any existing path.
   - A bare type change is stopped first by `ck_products_type_integrity`; the
     composite FK is the backstop for an otherwise valid STL row (proven in step 6).
3. **Should the price snapshot be refreshed when a merge or `PATCH` changes the
   quantity?** *Recommend no: the snapshot is set once, when the line is created.*
   Refreshing on a re-add would silently accept a price rise without the explicit
   checkout confirmation BR-026 and §7.2 require. `DELETE` then re-add is the way to
   take today's price.
4. **Re-adding an STL already in the cart, and STL `quantity > 1`.** *Recommend:*
   - a re-add with quantity 1 is an idempotent `200` no-op;
   - `quantity ≥ 2` is `422 QUANTITY_EXCEEDS_LIMIT` (api §29.4 and FR-05);
   - reword api §10.1's "forced to 1" to match.
5. **A merge that would exceed the cap: reject or clamp?** *Recommend reject with 422*
   and leave the cart unchanged. FR-05 says "a failed line update must not partially
   modify the cart". Clamping silently changes what the customer asked for.
6. **Lines whose product became hidden, deleted, unavailable or WhatsApp-only: keep and
   flag, or auto-remove?** *Recommend keep and flag* (`purchasable: false` plus a
   reason; name kept; slug, image and current price hidden):
   - `PATCH` on such a line is 422, and `DELETE` always works;
   - checkout (VS-023) **refuses** them with 422 and names every offending line, and
     never drops them silently (§3.6; tightened in Revision 2);
   - this matches the wishlist decision (VS-038 Q6);
   - silent removal would look like data loss.
7. **Maximum lines per cart?** *Recommend 50*, with a new code `422
   CART_LINE_LIMIT_REACHED` (`limit` in the body). It bounds the response and the
   checkout work while staying far above a real 3D-print order. The value is a code
   constant, not a setting; promote it to a setting only if the owner wants it
   admin-editable.
8. **Cart rate limit?** *Recommend 300 writes per hour per user*, in one bucket for
   `POST`, `PATCH` and `DELETE`, keyed by user id and failing closed.
   - Quantity steppers produce many `PATCH`es, so the wishlist's 120 is too tight.
   - Add 429 to the `DELETE` row in api §10.1.
9. **Take an explicit product row lock (`FOR SHARE`) while adding?** *Recommend no.*
   The `cart_items` insert's FK check still takes an implicit `KEY SHARE` on the
   product; §3.6 shows it cannot form a cycle.
   - The cart is a hint, and checkout revalidates everything (entities rule: "cart
     contents never prove that a Product remains purchasable").
   - A product lock would make admin edits and `wishlist_count` updates wait on
     shoppers.
   - It would add a second lock to the §3.6 contract.
   - The brief stale window is flagged in `CartRead` at once.
10. **`GET /cart` for a user with no cart: create a row, or return `id: null`?**
    *Recommend `id: null` and no write.* A read (especially by an unverified user, who
    may not write) must not create rows. The frontend treats `id` as informational.
11. **Should `CartRead` lines carry a cover image?** *Recommend yes.* It comes from the
    same single batched Catalog query (a `LEFT JOIN` to the live cover), so it costs no
    extra round trip, and a cart page without thumbnails is a frontend workaround
    waiting to happen. If declined, drop `cover` from `CartProduct` and the schema.
12. **`POST` with an unknown, hidden or deleted product id: 404 or 422?** *Recommend a
    uniform `422 PRODUCT_NOT_PURCHASABLE` with `reason: not_listed`.* api §10.1 lists no
    404 for `POST`, the body identifies a product rather than a cart resource, and one
    identical answer for all four cases reveals nothing about hidden products.
13. **Should VS-022 ship an STL-ownership stub that VS-023 fills in?** *Recommend no.*
    The slice rules say to "add a shared component only when the first real feature
    needs it". VS-023 inserts the check at the marked point in `add_item` (§3.4 step 5),
    together with `order_items` and the ownership index it reads.
14. **For the co-owner to confirm: no silent drops at checkout.** *Decided by the owner
    on 2026-10-16, awaiting the co-owner's confirmation.*
    - Lines that are `not_listed`, `unavailable`, `whatsapp_only` or `over_cap` make
      checkout answer 422, listing every offending line. They are never dropped.
    - The only drop is SRS §7.3 step 5's "STL acquired since adding". Even that must be
      reported to the customer in the checkout response, by product id.
    - If the co-owner prefers dropping non-purchasable lines, that contradicts SRS §7.3
      step 4 ("validate every line") and INV-07 ("rejected at checkout"), so it would
      need an SRS change first.
