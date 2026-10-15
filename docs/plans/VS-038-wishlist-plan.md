# VS-038 — Wishlist and Wishlist Analytics: Implementation Plan

**Status:** RE-BASELINED (implementation partially in progress — see "Changes since first draft")
**Date:** 2026-10-14; re-verified 2026-10-16; re-baselined 2026-10-16
**Planned against alembic head:** `2e89860f5274` (addresses_table, VS-026) — confirmed
still current and still the single head on 2026-10-16 (`alembic heads` → `2e89860f5274
(head)`; history chain: `cc87333ebe79` → `c2b3aae1cdee` (VS-033) → `2e89860f5274` (VS-026)).
This slice's migration's `down_revision` must be `2e89860f5274`, no longer a placeholder.

## Changes since first draft (2026-10-16 re-baseline)

- **Preflight, re-confirmed:** `git fetch --all --prune` shows only `origin/main`; no
  other remote branch; `gh pr list --state open` is empty. Nothing on GitHub touches
  VS-038 or VS-013. **However, this local branch (`feat/vs-038-wishlist`) already carries
  implementation commits from an earlier session**, which the chat preflight reports in
  full: `d34d55d` (`WishlistItem` domain entity + `WishlistProductUnavailableError`,
  step 2) and `4d61ca9` (`WishlistStore` Protocol + `ProductStore.get_many`/
  `top_by_wishlist_count`, step 3), plus an **uncommitted** `app/catalog/public.py`
  (`adjust_wishlist_count`, step 4) and its unit test. Steps 1–4 of §8 are therefore
  already done or in progress, not merely planned — confirm with the owner whether to
  continue from there or restart steps 2–4 against this re-baseline before touching the
  migration (step 6).
- **§3 exceptions correction:** the plan said "No new exceptions needed beyond what
  `ApiError` already covers." The committed code (step 2) already added
  `WishlistProductUnavailableError` to `app.engagement.domain.exceptions` — a domain
  exception the API layer maps to 404, matching the `ContactMessageNotFoundError`/
  `InvalidContactDetailsError` pattern VS-033 established. This is the correct call;
  the "no new exceptions" sentence in §3 is superseded by it.
- **§5 cursor precedent correction:** VS-033's actual merged `contact_messages.py`
  cursor is a **3-part** keyset — `(status, created_at, id)`, base64 of
  `"{status.value}|{created_at.isoformat()}|{id}"` — because the admin queue sorts by
  status first. Wishlist's own cursor has no status dimension, so the 2-part
  `(created_at, id)` design in §5 is still correct; only the citation of what
  `contact_messages.py` does is corrected here, not the wishlist design itself.
- **VS-026 (address book) checked for reusable conventions**, per this round's ask:
  `app/identity/api/addresses.py` has no cursor pagination and no rate limiter (a
  bounded, unpaginated personal list) — it offers nothing beyond the project's standard
  `ApiError`/422 shape already used throughout. VS-033's `contact_messages.py` and
  `admin.py`'s `admin_rate_limit` remain the closest precedents for this slice's cursor
  and rate-limiter ordering trick, as §5 already concluded.
- **ADR check:** ADR-025 (frontend contract decisions), ADR-026 (captcha refusal/outage),
  and ADR-027 (address book decisions) all read — none mentions wishlist or imposes a
  new constraint on this slice. §7's "no new ADR" stands.
- **`products.wishlist_count` + `ck_products_wishlist_count_non_negative` re-confirmed**
  present in `fc18b48a1780_products_table.py` — §1's claim holds.
- **Not touched by this re-baseline:** `docs/vertical-slice-plan.md`'s VS-038 row still
  reads "Not started", which is now stale given the in-progress code above — left as-is
  here since updating it is step 13's job, not this plan file's.

## 0. Preflight (see chat reply for the short form)

**2026-10-16 re-verification, superseding the note below:** `origin/main` advanced by
three commits since the first draft — VS-033 (`3e0af1b`, contact form + captcha,
migration `c2b3aae1cdee`) and VS-026 (`a859066`, address book, migration `2e89860f5274`)
both merged, plus ADR-025 (`8b16928`, no wishlist impact — see chat reply). Local `main`
fast-forwarded to `origin/main`; single alembic head confirmed: `2e89860f5274`. Neither
merged slice touches Catalog, so the `ProductStore`/`catalog.public` design in §3 is
unaffected; VS-033's `contact_messages.py` supplies a closer in-Engagement cursor
precedent than `product_cursor.py` — see the refinement in §5.

**Original 2026-10-14 note (superseded above):** No remote branch or open PR touched
VS-038 or VS-013. Single alembic head at the time: `cc87333ebe79_product_images.py`.

## 1. Scope and non-goals

**In scope** (per the plan table row `VS-038 | Wishlist and wishlist analytics | VS-013`,
SRS BR-108, F-030/F-103/F-104/F-123, FR-14, `api-endpoints.md` §14.2 and the
`/admin/analytics/wishlist` row):

- Customer-facing wishlist: add, remove, list own wishlist items.
- The `wishlist_items` table (soft delete, one active row per `(user, product)`).
- Maintaining `products.wishlist_count` (column, server default `0`, and
  `CHECK (wishlist_count >= 0)` — `ck_products_wishlist_count_non_negative` — both already
  added by `fc18b48a1780_products_table.py`, the baseline products migration; verified
  by reading that file. This slice is its first *writer*; no new column or CHECK needed).
- One admin read endpoint: `GET /api/v1/admin/analytics/wishlist` (totals + most-wishlisted),
  because the plan table assigns this specific route to VS-038, not to VS-043.

**Out of scope / excluded as VS-043's (Business analytics)**, even though VS-038's title
says "...and wishlist analytics": `/admin/analytics/overview`, `/revenue`,
`/recent-purchases`, `/customers`, `/top-rated-products`, `/stl-sales`,
`/custom-requests/funnel`, and any shared "reporting port" abstraction those endpoints
might standardize on. VS-043 depends on VS-029/030/031/036/039 — not on VS-038 — so no
such abstraction exists yet to reuse or to commit to; see owner question 1.

**Non-goals:** price-drop alerts (SRS §12.3, explicitly deferred to a future version),
reviews (VS-036), anything about carts (separate entity per domain-glossary).

## 2. API

| Method + Path | Auth | Request | Success | Errors | Notes |
|---|---|---|---|---|---|
| `GET /api/v1/me/wishlist` | `current_user` (any authenticated) | `cursor`, `limit` query params | `200 WishlistPage` | 401 | Cursor, default/only sort `-created_at`; active rows only |
| `PUT /api/v1/me/wishlist/{product_id}` | `current_verified_user` | — | `204` | 401, 403, 404, 429 | Idempotent insert-if-absent; updates `wishlist_count` |
| `DELETE /api/v1/me/wishlist/{product_id}` | `current_verified_user` | — | `204` | 401, 403, 404, 429 | Idempotent soft delete; updates `wishlist_count` |
| `GET /api/v1/admin/analytics/wishlist` | `require_admin` (+ MFA per ADR-017) | `limit` only — no `from`/`to`; default 20, max 100 | `200 WishlistAnalytics` | 401/404, 422 above max | Totals + most-wishlisted products |

Notes matching existing conventions:

- `GET /me/wishlist` uses `current_user`, not `current_verified_user`: the endpoint table
  marks it "Authenticated" (not "Verified Customer"), unlike the two write routes — an
  unverified user may read an empty list but not write (FR-14 negative case).
- 403 on the write routes is the unverified-user case (`require_verified_user`-style
  dependency, matching cart/offer/review write routes already gated the same way).
- 404 on the write routes: `product_id` does not exist, is soft-deleted (`deleted_at`
  set), or is not currently visible (`attributes.is_visible = false` — a separate column
  from `deleted_at`, confirmed by reading `app/catalog/domain/product.py`; SRS FR-14's
  given clause is "the product is visible"). Both "unknown" and "known but hidden" answer
  404 — telling a customer an archived/hidden product still exists leaks nothing useful
  and the SRS draws no finer line.
- **429 on both `PUT` and `DELETE`, one shared bucket** (decision, was "PUT only" in the
  prior draft): add/remove churn on the same product_id is one abuse shape, not two, so
  both routes consume the same per-user counter under one `key_prefix`. `GET` stays
  unlimited — a normal authenticated read with no documented rate limit in
  `api-endpoints.md`.
- All routes are versioned cents-free (no money involved) and need no `Idempotency-Key`
  header — `PUT`'s own idempotent-by-construction semantics cover retries, consistent
  with how `PUT` is used elsewhere in the SRS versus the explicit header required for
  checkout/refund.
- `GET /admin/analytics/wishlist` takes no `from`/`to`: neither the SRS nor
  `api-endpoints.md` defines what a date range would mean for a wishlist total (verified
  by reading both — see §10 Q2, now resolved). The maintained `wishlist_count` column has
  no time dimension to filter by; accepting the params and silently ignoring them would
  be the "silent no-op param" this follow-up explicitly rules out, so the route simply
  does not declare them. In their place, `limit` is explicit and bounded —
  **default 20, max 100, `422` above the max** — which is what actually satisfies
  `api-endpoints.md` line 641's "All analytics are read-only, Admin + MFA, bounded by
  explicit date ranges/limits": this route has no date range, so its bound is the limit.

### Schemas (new, in `app.engagement.api.schemas`)

- `WishlistItemRead { product_id, created_at, available: bool, name: str, slug: str | None, price_cents: int | None, currency: str | None, type: ProductType | None }`
  — `product_id`, `created_at`, `available`, `name` are always populated (so even an
  unavailable row identifies itself); the rest are populated only when `available` is
  `True`. No cover image: showing one would need a second batched cross-context port
  just for a thumbnail on a personal list view, and nothing in the SRS or
  `api-endpoints.md` requires one here (unlike the storefront grid) — deliberately
  trimmed rather than quietly reusing `ProductListItem` wholesale (see §5 on the batch
  read this implies). `available` is `False` when the product is soft-deleted or
  `is_visible = false` (§10 Q6, resolved: such rows stay in the list, reduced to id +
  name, rather than disappearing).
- `WishlistPage { items: list[WishlistItemRead], next_cursor: str | None }` — same envelope
  shape as `ProductPage`/`SearchSuggestionList` etc.
- `WishlistAnalytics { total_active: int, most_wishlisted: list[{product_id, name, slug, wishlist_count}] }`
  — `total_active` and `most_wishlisted` both include non-public (hidden/archived)
  products: `wishlist_count` is a maintained total of interest, and hiding a product from
  the storefront is a customer-visibility rule, not a reason to erase it from what the
  administrator sees (§10 Q6, resolved). `most_wishlisted`'s length is bounded by the
  request's `limit` (default 20, max 100, `422` above the max — §2).

## 3. Layers, function by function

### `app.engagement.domain`

- `WishlistItem` entity (dataclass): `id: UUID`, `user_id: UUID`, `product_id: UUID`,
  `created_at: datetime`, `updated_at: datetime`, `deleted_at: datetime | None`. No
  behaviour beyond `is_deleted` — there is no state machine here, just presence/absence
  (FR-14: "Wishlist absent ↔ present").
- No new exceptions needed beyond what `app.core.exceptions.ApiError` already covers
  (404/403/429 map directly).

### `app.engagement.application.ports` (Protocols, extending the existing file)

**Decision applied (this round): insert-only, not restore-then-insert.** A soft-deleted
`wishlist_items` row is never reactivated. Re-adding a product the customer previously
removed creates a brand-new row with a fresh `created_at` — which is also the *correct*
ordering behaviour: a product re-added today should sort as "wishlisted today" in
`-created_at` order, not resurface at its original add date. The old row stays, untouched,
as history (consistent with CLAUDE.md's blanket soft-delete rule — nothing here needs it
deleted or merged). This removes the two-statement restore-then-insert path entirely.

```python
class WishlistStore(Protocol):
    async def add(self, *, user_id: UUID, product_id: UUID) -> bool:
        """True if this call inserted a new active row; False if an active row already
        existed. Caller uses this to decide whether to adjust the aggregate — the whole
        reason idempotent PUT does not double-count."""
        ...

    async def remove(self, *, user_id: UUID, product_id: UUID) -> bool:
        """True if an active row was soft-deleted; False if there was none."""
        ...

    async def list_page(
        self, *, user_id: UUID, after: tuple[datetime, UUID] | None, limit: int
    ) -> list[WishlistItem]: ...
```

**Correction from the first draft:** `list_page` returns Engagement's own rows only —
no join to `products` inside Engagement's infrastructure. Reading `tests/unit/test_deep_architecture.py`
(`test_no_context_imports_another_contexts_infrastructure`) confirms it statically
forbids any `app.engagement.*` module importing `app.catalog.infrastructure` — a raw
SQL join would need `ProductModel` imported from exactly there, so it is not legal,
not merely discouraged. The API layer instead calls a new batched read,
`app.catalog.application.ports.ProductStore.get_many(ids: list[UUID]) -> list[Product]`
(one `WHERE id IN (...)` query, added to the existing Protocol), with the wishlist
route's product ids collected from `list_page`'s results first. This is one extra
query per page, not one per item — see §5.

**Confirmed (this round): `get_many` must not filter by visibility or soft-delete.**
`get_by_id`'s existing implementation (`product_repository.py`) has no `deleted_at`
filter and returns the row regardless — `get_many` is the same query widened to
`WHERE id IN (...)`, so it returns a non-public product's full `Product` entity,
`deleted_at` and `attributes.is_visible` included. That status is exactly what
`add_to_wishlist`'s `available` computation needs (§2's schema) — if `get_many` instead
filtered to visible/live products only, a non-public product would come back missing
from the result set with no way to tell "not found" apart from "filtered out", and
`available` could not be computed at all. The plan's first draft did not filter these
out; this is a confirmation, not a fix.

### `app.engagement.application.services.wishlist` (new, mirrors `notification_writer.py`)

**Decision applied (§10 Q3, resolved):** the cross-context write is one function,
`app.catalog.public.adjust_wishlist_count(session, product_id, delta)`, taking the
*caller's* `AsyncSession` — confirmed feasible by reading `app.engagement.public.create_notification`,
which already takes `session: AsyncSession` as its first argument and does **not**
commit, so a business mutation and the notification announcing it land in one
transaction (its own docstring states this explicitly). The wishlist write reuses
exactly that shape: both ports are called inside the API route's existing
request-scoped session, before the route commits.

The visibility check (for the 404 case) is a plain **read**, not a write, so it does not
go through `catalog.public` at all — it goes through the already-allowed
`app.catalog.application.ports.ProductStore` Protocol (`get_by_id`), with Catalog's API
layer supplying its concrete repository the same way Catalog's own commands do. This
keeps `catalog.public` at exactly the one function the decision calls for.

- `async def add_to_wishlist(session, store: WishlistStore, products: ProductStore, *, user_id, product_id) -> None`
  1. `product = await products.get_by_id(product_id)`; if `product is None`,
     `product.is_deleted`, or not `product.attributes.is_visible` → raise
     `ProductNotFoundError` → mapped to 404.
  2. `changed = await store.add(user_id=user_id, product_id=product_id)`.
  3. If `changed`: `await adjust_wishlist_count(session, product_id, +1)`.
  4. No commit here — caller's session/transaction owns that.
- `async def remove_from_wishlist(...)` — symmetric: `removed = await store.remove(...)`;
  if `removed`: `await adjust_wishlist_count(session, product_id, -1)`. No visibility
  check on remove — a customer must be able to remove a wishlist entry for a product
  that has since gone non-public (§10 Q6).
- The counter only ever moves when a row's live/soft-deleted state actually flips —
  `add`/`remove` returning a bare `bool` for "did state change" is what makes
  "repeated call → delta of 0" trivially true by construction, not by a separate
  before/after comparison the service would have to get right.

### `app.catalog.public` (new module; today only `app.catalog.application.ports` exists)

```python
async def adjust_wishlist_count(session: AsyncSession, product_id: UUID, delta: int) -> None:
    """delta is +1 or -1, from a caller that already confirmed a real state change.
    Single atomic UPDATE; its own row lock is the serialization point, matching how
    save_if_version uses the statement itself rather than a manual lock+save pair."""
    await session.execute(
        update(ProductModel)
        .where(ProductModel.id == product_id)
        .values(wishlist_count=ProductModel.wishlist_count + delta)
    )
```

No visibility filter in the `WHERE` clause: a decrement must still land even if the
product became non-public between add and remove, because `wishlist_count` tracks total
interest regardless of current visibility (§10 Q6). The pre-existing
`ck_products_wishlist_count_non_negative` CHECK (confirmed already in
`fc18b48a1780_products_table.py`, §1) is defence-in-depth — Engagement's own call
discipline (never decrementing without a confirmed `remove` state change) is what
actually keeps it non-negative. No new CHECK needed, and no second function is added to
this module; a future slice needing another Catalog write grows this file rather than
reaching around it.

### `app.engagement.infrastructure`

- `WishlistItemModel` in `models.py`: table `wishlist_items`, columns per
  `database-design.md` §12.2 (`id`, `user_id` FK, `product_id` FK, `deleted_at`,
  `created_at`, `updated_at`), partial unique index `(user_id, product_id) WHERE deleted_at IS NULL`.
- `WishlistRepository` in `repositories.py` implementing `WishlistStore`:
  - `add` (insert-only, this round's decision — no restore path):
    `INSERT INTO wishlist_items (id, user_id, product_id, created_at, updated_at) VALUES (gen_random_uuid(), :u, :p, now(), now()) ON CONFLICT (user_id, product_id) WHERE deleted_at IS NULL DO NOTHING RETURNING id`.
    One statement. `True` iff a row was returned (a fresh insert happened); `False` if the
    insert hit the conflict (an active row for `(user_id, product_id)` already exists —
    the common idempotent-repeat case). A product the customer previously removed and is
    now re-adding has no conflicting *active* row (the old one is soft-deleted, excluded
    by the partial index's `WHERE` clause), so the insert succeeds and creates a **new**
    row with its own `id` and a fresh `created_at` — the old, soft-deleted row is left
    alone as history, never touched, never reused.
  - `remove`: `UPDATE wishlist_items SET deleted_at = now(), updated_at = now() WHERE user_id = :u AND product_id = :p AND deleted_at IS NULL RETURNING id`; `True` iff a row returned.
  - `list_page`: `SELECT ... FROM wishlist_items WHERE user_id = :u AND deleted_at IS NULL`,
    ordered `(created_at DESC, id DESC)` with the keyset predicate from the decoded
    cursor, `LIMIT :limit + 1` to compute `next_cursor` — **no join to `products`**: see
    the correction in §3's port section above. The route layer takes this page's
    `product_id`s and calls `ProductStore.get_many(ids)` once to fill in `name`/
    `slug`/`price_cents`/`currency`/`type`/`available` for the response.
- A small, read-only wishlist-analytics query (a function, not a repository, since it is
  single-purpose): `total_active = count(*) FROM wishlist_items WHERE deleted_at IS NULL`
  (Engagement's own table, no cross-context concern). `most_wishlisted` is **not** a raw
  `SELECT ... FROM products` either, for the same architecture-test reason as `list_page`:
  it calls a second new `ProductStore` method,
  `top_by_wishlist_count(limit: int) -> list[Product]`
  (`SELECT * FROM products ORDER BY wishlist_count DESC, id LIMIT :n`, implemented in
  Catalog's `ProductRepository`), which reads the maintained `products.wishlist_count`
  column directly rather than recomputing from `wishlist_items` — matching the plan
  table's "Analytics reads the maintained counts" line — but from *inside* Catalog's own
  infrastructure layer, where that import is legal.

### `app.engagement.api`

- `wishlist.py` router, mounted under `/api/v1/me/wishlist` (customer) — new file,
  alongside the existing `notifications.py` pattern (one router module per sub-resource).
- Admin route lives wherever the rest of `/api/v1/admin/analytics/*` will eventually live;
  since none of that namespace exists yet (VS-043 not built), this slice creates
  `app/engagement/api/admin_analytics.py` with just the one wishlist route, mounted into
  `app/api/v1/admin.py` the same way `audit_logs_router`/`settings_router` are. VS-043
  will either extend this module or supersede it — flagged as owner question 1.
- Dependencies: `current_user`, `current_verified_user`, `require_admin` all imported
  from `app.identity.public`, per CLAUDE.md's reuse list — no new auth code.

## 4. Database

**Table `wishlist_items`** (new migration, `down_revision = 2e89860f5274`, the current head):

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | UUID | No | PK, server-generated (matches ADR-002) |
| `user_id` | UUID | No | FK → `users.id`, `ON DELETE RESTRICT` (anonymisation touches the row via VS-045, not a cascade delete) |
| `product_id` | UUID | No | FK → `products.id`, `ON DELETE RESTRICT` |
| `deleted_at` | TIMESTAMPTZ | Yes | soft-delete marker |
| `created_at` | TIMESTAMPTZ | No | server default `now()` |
| `updated_at` | TIMESTAMPTZ | No | server default `now()`, app-maintained on update |

Constraints/indexes:

- `UNIQUE (user_id, product_id) WHERE deleted_at IS NULL` — the **DB-enforced** invariant
  that makes the "exactly one active row per user/product" rule survive concurrent
  `PUT`s, per CLAUDE.md's "application checks lose races" rule. This is the load-bearing
  constraint for this whole slice.
- `CHECK` none needed beyond the FKs and NOT NULLs — there is no status enum here.
- Index `(user_id, created_at DESC, id DESC) WHERE deleted_at IS NULL` to serve
  `GET /me/wishlist`'s keyset pagination without a sort.
- Index `(product_id) WHERE deleted_at IS NULL` to serve the (rare, admin-triggered)
  "how many people wishlisted this product" cross-check and any future product-detail
  "N people wishlisted this" display, if one is ever added — cheap to add now, expensive
  to add as a follow-up migration once the table is large. Confirm this isn't
  over-building: it is one extra index on a FK the planner will want regardless of
  display plans, not a speculative feature.
- **No per-user cap column/constraint (§10 Q4, resolved: no).** The `UNIQUE (user_id,
  product_id) WHERE deleted_at IS NULL` constraint already bounds each user's active
  wishlist to at most the number of distinct products in the catalogue — one row per
  product, no duplicates possible — so a cap would only ever bind below that natural
  ceiling, and nothing in the SRS asks for a tighter one. Adding one unasked would be
  scope beyond what the SRS specifies for this phase (CLAUDE.md working-style rule).

`products.wishlist_count` already exists (added by an earlier migration as a
placeholder aggregate) — no migration needed for it, only its first writer (§3).

**Concurrency:** two concurrent `PUT`s for the same `(user, product)` race on the
partial unique index — including when the product was previously removed (no conflicting
active row exists until the first of the two commits its insert): the loser's
`INSERT ... ON CONFLICT DO NOTHING` returns no row, `add` returns `False`, and the
aggregate is incremented exactly once, not twice, regardless of whether this is a
first-ever add or a re-add after a prior removal. This is the scenario the plan table's
own "Done when" line (`wishlist_count` always equals the number of live rows) and its
concurrency test target directly — see §6 for the re-add race specifically.

## 5. Performance and abuse

- **Pagination:** cursor-based, `(created_at, id)` keyset, same opaque-base64 cursor
  shape as `product_cursor.py`'s `encode_cursor`/`decode_cursor` but simplified — no
  search mode, no multi-sort, since the endpoint has exactly one order (`-created_at`,
  matching the api-endpoints table's "default `-created_at`" and the fact it lists no
  other sort option). **Refinement (VS-033 landed on main first): model the cursor
  helper on `app.engagement.api.contact_messages`'s own file-local
  `_encode_cursor`/`_decode_cursor`, not Catalog's `product_cursor.py`.** That pattern
  is now a direct, in-context Engagement precedent — base64 of `f"{created_at.isoformat()}|{id}"`,
  no search-mode payload — rather than reaching across to Catalog's richer (multi-sort,
  search-aware) cursor. Reversibility is the same guarantee either way: full microsecond
  `isoformat()` precision plus the row `id` as a deterministic tie-breaker, so nothing is
  lost round-tripping through the opaque base64 payload. A forged/foreign/tampered
  cursor must never reach the database as a malformed value — `contact_messages.py`'s
  own `_decode_cursor` already turns a `ValueError`/`binascii.Error`/`UnicodeDecodeError`
  into a `RequestValidationError` (422), the same shape to reuse here (see §6 test).
- **Rate limiting:** one shared bucket, `key_prefix="wishlist"`, keyed by **user id**
  (via `claims.user_id` from `current_verified_user`, read before the limiter runs — same
  ordering trick as `admin_rate_limit`, so an unverified or anonymous caller never
  consumes the budget and never gets a 429 where a 401/403 belongs), consumed by both
  `PUT` and `DELETE`. Not IP-keyed: same reasoning as `admin_rate_limit` in
  `app/api/v1/admin.py` — until VS-020's forwarded-IP work covers this route too, an IP
  key would throttle every customer behind a shared IP together. **Limit: 120/hour**
  (§10 Q5, resolved) — generous enough that normal browsing never hits it, tight enough
  to stop a scripted enumeration of every product id. **Fail-closed, matching the
  existing limiter exactly** (confirmed by reading `app/api/errors.py`): `enforce_rate_limit`
  does not catch its own Redis call failing, and `redis.exceptions.ConnectionError`/
  `TimeoutError` are both listed in `DEPENDENCY_UNAVAILABLE_ERRORS`, so a Redis outage
  surfaces as `503 SERVICE_UNAVAILABLE`, not a silently-allowed request — this slice adds
  no new behaviour here, it just reuses `rate_limiter`/`enforce_rate_limit` unchanged.
- **N+1 on product joins:** fixed by batching, not by joining — see the correction in §3:
  `list_page` returns Engagement's own rows, and the route calls
  `ProductStore.get_many(product_ids)` once per page (one query, `WHERE id IN (...)`),
  not once per item. This is the same "one query per page" shape
  `storefront_query.py` already uses for the catalogue list, achieved here across a
  context boundary via a batched port method instead of a SQL join.
- **Cross-context access:** confirmed against `tests/unit/test_deep_architecture.py`
  (`test_no_context_imports_another_contexts_infrastructure`) that Engagement may import
  `app.catalog.public` and `app.catalog.application.ports` only, never
  `app.catalog.infrastructure`. All three Catalog touchpoints in this plan honour that:
  the one write (`catalog.public.adjust_wishlist_count`), and the two reads
  (`ProductStore.get_by_id` for the visibility check, `ProductStore.get_many`/
  `top_by_wishlist_count` for the list and analytics reads) all go through
  `app.catalog.application.ports`, never a raw join against `ProductModel`.
- **Admin analytics date range:** resolved — no `from`/`to` on this route at all (§2,
  §10 Q2). In their place, `limit` is explicit and bounded: default 20, max 100, `422`
  above the max — this is what satisfies `api-endpoints.md` line 641's "bounded by
  explicit date ranges/limits" rule for a route that has no date range to bound.

## 6. Tests

**Unit** (`tests/unit/`):
- `WishlistItem` domain entity: `is_deleted` behaviour.
- `add_to_wishlist`/`remove_from_wishlist` services against a fake `WishlistStore` +
  fake `ProductStore`: the "changed → adjust count, unchanged → don't" branching, the
  404-on-not-visible path, with the fakes recording exactly one call to
  `adjust_wishlist_count` per logical state change — explicitly including **repeat add
  = delta 0** and **repeat remove = delta 0** as their own asserted cases, not just
  implied by the "changed" branch.
- **Add of a hidden/non-visible product → 404**, asserted against the fake `ProductStore`
  returning a product with `is_visible = False` (and a second case for `is_deleted = True`).
- Cursor encode/decode round-trip, mirroring `product_cursor.py`'s own test style.
- **Tampered cursor → 4xx, never 500**: every malformed-input case `_decode` itself
  tests (bad base64, truncated JSON, wrong `sort` tag, non-UUID id, out-of-range
  timestamp) re-asserted for the wishlist cursor variant, confirming each raises
  `RequestValidationError` (422) and none can reach the database layer unvalidated.
- Architecture test (extend `test_deep_architecture.py`'s existing assertions, don't
  rewrite it): Engagement only imports Catalog through `app.catalog.public` /
  `app.catalog.application.ports`; nothing in `app.engagement` imports
  `app.catalog.infrastructure`. This is the test that caught the join-based `list_page`
  design in the first draft of this plan — keep it exercising the wishlist module
  specifically, not just relying on the existing parametrized sweep to happen to cover it.

**Integration** (`tests/integration/`, real Postgres via `tests/conftest.py` fixtures):
- `PUT` on a visible product inserts one active row and increments `wishlist_count` by 1.
- Repeated `PUT` (same user/product) is a no-op on the second call: row count and
  `wishlist_count` both unchanged (the "counts once" requirement from the plan table).
- `DELETE` then `PUT` creates a **new** row (insert-only, this round's decision — not a
  restore): a different `id` from the original, a fresh `created_at` later than the
  original `created_at`, the original row still present with `deleted_at` set as
  history, and `wishlist_count` incremented again (back to 1, not 2).
- Add/remove/add/remove/add (three full cycles) leaves exactly **one** active row and
  two soft-deleted history rows for that `(user, product)`, and `wishlist_count` equal
  to 1 — not 3, not 0 — confirming the counter tracks current state, not cumulative
  add/remove events.
- Repeated `DELETE` is a no-op on the second call.
- `PUT`/`DELETE` against a nonexistent, soft-deleted, or non-visible `product_id` → 404.
- `PUT` by an unverified user → 403; `GET` by an unverified user → 200 with their
  (possibly empty) list, since `GET` only requires `current_user`.
- `GET /me/wishlist` pagination: a second page via `next_cursor` returns the next
  slice in `-created_at` order with no duplicates/gaps against a seeded set larger
  than one page.
- `GET /me/wishlist` never returns another user's items (isolation check, same
  shape as the existing "own reviews/addresses only" tests elsewhere).
- `GET /me/wishlist` keeps an item whose product later became non-public: the row
  stays, `available = False`, only `product_id`/`created_at`/`name` populated (§10 Q6).
- `GET /admin/analytics/wishlist` requires admin + MFA (401/404 boundary per
  ADR-017, same assertion pattern as other admin routes). `limit` defaults to 20 when
  omitted, and a `limit` above 100 gives 422 (§2, §10 Q2 — the route's signature simply
  has no `from`/`to` parameters; passing them has no effect, which is different from
  declaring them and then ignoring them). Totals and most-wishlisted ordering match
  seeded `wishlist_count` values, **including a non-public product that must still
  appear** (§10 Q6 — non-public products count).
- **Database constraint test against real Postgres** (not mocked, per CLAUDE.md):
  a direct second `INSERT` attempting to bypass the partial unique index is rejected
  by Postgres itself, independent of the application path.

**Concurrency** (`tests/concurrency/`, `meet_or_fail` barrier):
- N concurrent `PUT`s for the same `(user, product)` racing at the barrier: exactly
  one active row exists afterward, and `wishlist_count` increased by exactly 1, not N
  (the scenario in §4) — this is the plan table's named concurrency test and should be
  the heaviest-covered case in this slice.
- Concurrent `PUT` and `DELETE` for the same pair: whichever commits last decides the
  final `deleted_at` state, and `wishlist_count` ends consistent with that final state
  (no permanently-drifted counter).
- Concurrent `PUT`s for the *same user, different products* (control case): both
  succeed, counts on each product move independently — confirms the lock granularity
  is per-product, not an accidental global serialization.
- **New test (this round): two concurrent `PUT`s on a previously-removed product.**
  Seed one soft-deleted row for `(user, product)` (a prior remove), then race two `PUT`s
  for the same pair at the barrier. Exactly one succeeds in inserting (the other's
  `INSERT ... ON CONFLICT DO NOTHING` returns no row, since neither sees the other's
  not-yet-committed row as a conflict target until one commits); exactly one active row
  exists afterward, `wishlist_count` is +1 from its pre-race value (not +2), and neither
  caller observes a 500 — this is the race the insert-only redesign (§3) specifically
  targets, since it is the one case the old restore-then-insert design handled with two
  separate statements instead of one.
- **New invariant test (this follow-up):** many distinct users racing `PUT`/`DELETE`/
  re-`PUT` against **one shared product** at the barrier, in a mix (some adding for the
  first time, some removing, some re-adding after a prior remove) — after all complete,
  `products.wishlist_count` for that product must equal
  `SELECT count(*) FROM wishlist_items WHERE product_id = :id AND deleted_at IS NULL`
  exactly. This is the general form of the "Done when" line (not just two callers, not
  just one action type) and is the test most likely to catch a delta computed from a
  stale read rather than from `add`/`remove`'s own return value.

**Smoke** (`tests/smoke/`, `pytest -m smoke`):
- One happy-path `PUT` → `GET` list → `DELETE` → `GET` list round trip, plus one admin
  analytics read — matching the shallow "does the slice work at all" level of existing
  smoke coverage.

## 7. Docs and ADRs needed

- No new ADR: this slice makes no architecture-level decision beyond ones CLAUDE.md
  already states (soft delete, DB-enforced uniqueness, cross-context ports) — it
  *applies* existing decisions to a new entity, the same way VS-036 reviews would. The
  one genuinely new structural piece — introducing `app.catalog.public`, resolved to a
  single `adjust_wishlist_count` function (§10 Q3) — is documented as a one-line note in
  that file's own docstring (mirroring `app.engagement.public`'s), not a standalone ADR.
- Update `docs/vertical-slice-plan.md`'s VS-038 status row only (per existing convention
  — the table is the single source of per-slice status, not this plan doc).
- No README change expected (no new local-dev step, no new port, no new container).

## 8. Implementation steps, in order

1. ~~Confirm VS-033's migration head~~ — done at the 2026-10-16 re-verification: both
   VS-033 (`c2b3aae1cdee`) and VS-026 (`2e89860f5274`) merged; current single head is
   `2e89860f5274`, re-confirmed with `alembic heads` immediately before STEP 2.
2. Domain: `WishlistItem` entity (`app/engagement/domain/entities.py`, extending the
   existing file).
3. Application ports: `WishlistStore` Protocol (`app/engagement/application/ports.py`);
   extend Catalog's `ProductStore` Protocol with `get_many(ids)` and
   `top_by_wishlist_count(limit)` (`app/catalog/application/ports.py`).
4. `app.catalog.public`: the one function, `adjust_wishlist_count`, with its own unit
   test against a fake session and an integration test against real Postgres. The
   visibility check and the two new reads from step 3 are implemented as
   `ProductRepository` methods (Catalog's existing concrete class), not as anything new
   in `catalog.public`.
5. Application service: `add_to_wishlist` / `remove_from_wishlist`
   (`app/engagement/application/services/wishlist.py`), unit-tested against fakes for
   `WishlistStore` and `ProductStore` from step 3.

   **CHECKPOINT:** by this point the riskiest design decision — the Catalog/Engagement
   boundary for the aggregate write (owner question 3) — is implemented and unit-tested
   against fakes, before any migration or real route exists. Confirm with the owner
   that the `catalog.public` shape is acceptable before continuing; a change here after
   the migration and routes exist is a bigger rewrite than a change here is now.

6. **Migration**: `wishlist_items` table, indexes, partial unique constraint — placed
   this late (not first, unlike most slices) because the schema is simple and fully
   determined by step 2–3's domain/port shapes; nothing upstream depends on the table
   existing earlier, and putting it after the risky design checkpoint avoids migrating
   twice if the checkpoint changes the column set.
7. Infrastructure: `WishlistItemModel`, `WishlistRepository` (the insert-only `add` and
   `remove` from §3), wired against the real migration; Catalog's
   `ProductRepository.get_many`/`top_by_wishlist_count` implementations.
8. Infrastructure: `list_page`'s (Engagement-only) query and the simplified cursor
   helper (modeled on `product_cursor.py`); the route-level batching of `list_page`'s
   product ids through `ProductStore.get_many`.
9. API: customer router (`GET`/`PUT`/`DELETE` on `/me/wishlist*`), wired to
   `current_user`/`current_verified_user`, the shared per-user `PUT`+`DELETE` rate
   limiter (120/hour, one bucket).
10. Infrastructure + API: the wishlist-analytics query function and the admin route,
    mounted into `app/api/v1/admin.py`.
11. Integration tests (§6), then concurrency tests (§6) — concurrency last because it
    exercises the full stack end to end and is slow to iterate on.
12. Full checks (`ruff`, `mypy --strict`, `pytest tests/unit`), then integration +
    concurrency + smoke suites locally (CLAUDE.md: hooks don't run these; run them
    before any PR).
13. Update the VS-038 status row in `docs/vertical-slice-plan.md`.

## 9. Risks

- **Boundary drift**: introducing `app.catalog.public` as a single-function module is
  easy to get right now and easy to get wrong later if VS-043 or a future slice adds
  ad hoc Catalog reads elsewhere in Engagement instead of growing this file — worth a
  one-line note in the module docstring warning future authors, same style as other
  `public.py` files' docstrings already do.
- **Unbounded row growth from repeated add/remove cycles** (this round's insert-only
  decision, §3/§4): since a removed-then-re-added product always inserts a new row
  rather than reactivating the old one, a customer who adds and removes the same product
  repeatedly leaves one soft-deleted row behind per cycle. This is accepted and correct
  per CLAUDE.md's blanket soft-delete rule (history is kept, nothing is merged away), and
  the shared 120/hour rate limit on `PUT`+`DELETE` (§5) already bounds how fast one
  customer can generate them; no separate cap is added for this reason alone.
- **Admin analytics scope creep**: the single wishlist analytics route is easy to grow
  into "might as well add overview/revenue now since I'm touching admin analytics" —
  explicitly out of scope per §1; resist it even if it looks like free reuse.
- **wishlist_count already exists with no writer**: if any other code path already
  assumes it is always 0 (e.g., a test fixture, a storefront sort using it as a
  secondary key), that assumption breaks the moment this slice ships a real writer —
  worth a targeted search during implementation, not just at planning time. The CHECK
  constraint already in place (§1) makes "went negative" fail loudly, not silently.
- **Batched-read redesign (this follow-up):** `list_page` no longer joins; it returns
  Engagement-only rows and the route makes one extra `ProductStore.get_many` call. This
  is a real second query per page, not a join — correct per the architecture test, but
  worth confirming at implementation time that `get_many` is actually `WHERE id IN (...)`
  and not, by an easy mistake, implemented as a loop over `get_by_id` inside the adapter.

## 10. Owner questions

All six resolved this follow-up round; kept here (not deleted) for traceability of why
each landed where it did.

1. **Does `/admin/analytics/wishlist` belong permanently in Engagement, or will VS-043
   relocate/absorb it into a shared analytics module once that slice exists?**
   **RESOLVED: stays in Engagement.** It's Engagement's own data — totals and
   most-wishlisted products derived from `wishlist_items`/`products.wishlist_count`, not
   a cross-context rollup like VS-043's revenue reports. VS-043 decides for itself later
   whether to import it, move it, or leave it alone; this slice does not block on that.

2. **Exact `WishlistAnalytics` response field names, and whether `from`/`to` filters
   anything or is accepted-but-ignored.**
   **RESOLVED: no `from`/`to` at all.** Verified neither the SRS nor `api-endpoints.md`
   defines any date-range semantics for this specific route (§A4 in the chat reply) — a
   silent no-op param is explicitly ruled out, so the route simply does not declare the
   params rather than accepting and ignoring them. Shape:
   `{ "total_active": int, "most_wishlisted": [{"product_id", "name", "slug", "wishlist_count"}] }`,
   `limit` only.

3. **Is introducing `app.catalog.public` (new file) the right call, versus extending
   `app.catalog.application.ports.ProductStore`?**
   **RESOLVED: `app.catalog.public`, exposing exactly one function,
   `adjust_wishlist_count(session, product_id, delta)`, running in the caller's
   transaction** — confirmed feasible by `app.engagement.public.create_notification`'s
   existing `session: AsyncSession` parameter and no-commit contract (§A3). The
   visibility check and the two batched reads this plan needs go through
   `ProductStore` via `application.ports` instead, so `catalog.public` does not grow a
   second function for them.

4. **Should there be a per-user wishlist size cap?**
   **RESOLVED: no.** The `UNIQUE (user_id, product_id) WHERE deleted_at IS NULL`
   constraint already bounds each user's active wishlist to at most the catalogue size —
   one row per product — so a cap would only bind tighter than that for no SRS-stated
   reason; out of scope for this phase (CLAUDE.md working-style rule).

5. **Rate limit numbers for `PUT`/`DELETE /me/wishlist/{product_id}`.**
   **RESOLVED: 120/hour per user id, one shared bucket for both `PUT` and `DELETE`**
   (add/remove churn on the same product is one abuse shape). Fails closed exactly like
   the existing limiter — a Redis outage is `503`, not a silent pass (§A3/§5).

6. **Does a non-public product's existing wishlist entry disappear from
   `GET /me/wishlist`, or stay visible with reduced/flagged info? Do non-public products
   count in admin analytics?**
   **RESOLVED: stays visible, reduced to id + name; counts in analytics: yes.** Unlike
   the storefront list (where hidden/deleted products must not appear to *other* users),
   this is the owning customer's own saved-item list, not a discovery surface — dropping
   an item the customer chose to save would look like data loss. `PUT` on a non-public
   product still answers 404 (can't *add* what isn't public); only an existing entry
   survives the product going non-public, and only an explicit `DELETE` removes it.
   `wishlist_count`/`most_wishlisted` include non-public products because the count
   tracks total interest, not current storefront eligibility.
