# ADR-029: Cart - hard-deleted lines, a type snapshot behind a composite FK, a first-add price snapshot, one cart lock and no product locks, a 50-line cap

**Status:** Accepted
**Date:** 2026-10-16
**Source basis:** Owner decisions of 2026-10-16 on the VS-022 owner questions (Q1 to Q14, [`../plans/VS-022-mixed-cart-plan.md`](../plans/VS-022-mixed-cart-plan.md) §10); SRS BR-018, BR-020 to BR-026, §7.1 to §7.3, §21.2, INV-07 to INV-09; FR-05; [ADR-022](ADR-022-storefront-commerce-capabilities.md); [ADR-024](ADR-024-cash-on-delivery-and-courier-priced-shipping.md) decision 9; [ADR-025](ADR-025-frontend-contract-decisions.md); [ADR-027](ADR-027-address-book-decisions.md)

## Context

VS-022 builds the persistent mixed cart. Five things the specification left open needed a decision:

- **Deleting lines.** BR-018 says nothing is hard-deleted, but the retention table in `database-design.md` lists cart data as "mutable operational data; cleanup allowed".
- **The STL rule in the database.** SRS §21.2 lists "STL line quantity = 1" as a database invariant, and `database-design.md` §8.2 calls the needed type snapshot "not required".
- **Which price a merge keeps.**
- **How checkout's cart lock fits ADR-024's lock order.**
- **How large a cart may grow.**

## Decision

1. **Cart lines are hard-deleted.** `DELETE /cart/items/{product_id}` and checkout's "clear the cart" remove rows, under a plain `UNIQUE (cart_id, product_id)` (INV-09). This is an explicit exception to BR-018:
   - nothing reads a removed line;
   - no audit, history or ownership depends on one;
   - soft delete would need a partial index, `deleted_at` filters everywhere, and an ever-growing table.

   The `carts` row itself is never deleted, only emptied. Its FK to `users` is `ON DELETE CASCADE`, so the never-verified purge is never blocked.
2. **The STL rule is enforced by the database.**
   - `cart_items.product_type` is snapshotted from the product.
   - `CHECK (product_type <> 'stl' OR quantity = 1)` holds the quantity.
   - A composite foreign key `(product_id, product_type) → products (id, type)` (`ON UPDATE RESTRICT`, on a new `UNIQUE (products.id, type)`) proves the snapshot equals the product's real type.
   - Two layers stop a type change: a bare `SET type` breaks `ck_products_type_integrity` first, and the composite FK is the backstop for an otherwise valid row.
   - No code path updates `products.type` today.
3. **Snapshots and caps:**
   - The price snapshot is taken when a line is created and kept on merges and quantity changes. `DELETE` then re-add takes today's price.
   - **The snapshot is display-only.** Checkout charges the live `products.price_cents`, recomputed server-side, and uses the snapshot only to detect a change (`409 CART_PRICE_CHANGED`).
   - The physical cap is read live, never snapshotted. A line above the current cap is flagged `over_cap`.
4. **One cart lock, taken first, and no product locks.**
   - Every cart write runs `INSERT INTO carts … ON CONFLICT (user_id) DO NOTHING` (on a first add), then `SELECT … FROM carts WHERE user_id = :uid FOR UPDATE`, before any read.
   - It needs READ COMMITTED, the application's level, so two concurrent first adds both succeed.
   - Cart code takes no explicit lock on `users`, `orders` or `products`; its inserts take only the implicit foreign-key `KEY SHARE`.
   - Checkout's order is: idempotency record → cart → (VS-028) address `FOR SHARE` → phone advisory lock → INSERT order.
   - VS-029 and VS-031 lock the cart only after their `orders` locks, as ADR-024 decision 9 already states. Checkout never locks an existing order, so the two orders cannot cycle.
5. **A cart holds at most 50 lines.** A new 51st product is `422 CART_LINE_LIMIT_REACHED` (`limit`); merging into an existing line is still allowed. The limit is a constant, not a setting.
6. **Lines whose product can no longer be bought stay, flagged.**
   - `purchasable: false` plus `unpurchasable_reason` (`not_listed`, `unavailable` or `whatsapp_only`).
   - A line that is not listed keeps its name but loses its slug, current price, cap and cover.
   - `PATCH` on such a line is refused, and `DELETE` always works.
   - **Checkout never drops them silently** (Q14). It answers 422 and names every offending line, `over_cap` lines included. The only drop is SRS §7.3 step 5's STL acquired since adding, and the checkout response names it.
7. **Refusals reveal nothing.** An unknown, deleted, hidden or inactive-category product answers one identical `422 PRODUCT_NOT_PURCHASABLE` with `reason: not_listed`. The cart is never looser than ADR-022's `can_add_to_cart`, because both come from `capabilities()` and from the one storefront visibility predicate, `listed_predicate()`.
8. **Rate limit:** 300 writes per hour per user, one bucket for `POST`, `PATCH` and `DELETE`, keyed by user id (never by IP), failing closed. Reads are not limited.

## Consequences

+ No cart can hold a duplicate line, an STL quantity above 1, or a line with the wrong type, even via SQL.
+ Concurrent adds serialise per cart: two `+3` adds against a cap of 5 give one line of 3 and one 422. With the lock removed, 14 of 15 runs hit a unique-index 500.
+ The frontend sees every reason a line cannot be bought before checkout does.
− A customer who re-adds after a price rise still sees `price_changed: true` until checkout; the UI must explain it.
− `uq_products_id_type` adds one index to `products`, and a product in any cart can no longer change type even through a future admin path.
− `MAX_CART_LINES` is fixed in code; changing it needs a deploy.

## Alternatives rejected

- **Soft-deleted cart lines** — history no one reads, and a partial unique index in place of a plain one.
- **Refreshing the snapshot on a merge** — silently accepts a price rise without the confirmation BR-026 requires.
- **Clamping an over-cap add** — changes what the customer asked for; FR-05 forbids a partial update.
- **`FOR SHARE` on the product while adding** — makes admin edits and wishlist counters wait on shoppers, adds a second lock to the contract, and checkout revalidates anyway.
- **Auto-removing lines that became unbuyable** — looks like data loss to the customer.
