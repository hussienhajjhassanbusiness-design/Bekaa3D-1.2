# ADR-048: Accepted payment methods per product - each physical product accepts online, cash or both, a cart pays only by a method every line accepts, and each order line snapshots what its product accepted (VS-049)

**Status:** Accepted (2026-10-31, VS-049).
**Date:** 2026-10-31
**Source basis:** Owner request of 2026-10-31 and owner approval of the VS-049 plan's recommendations (Q1-Q8); SRS BR-001, BR-004, BR-140, BR-141, BR-145, §6.1, §6.2, §7.3, §7.4, §9.8.1; [ADR-024](ADR-024-cash-on-delivery-and-courier-priced-shipping.md) d2; [ADR-038](ADR-038-physical-checkout-and-cash-eligibility.md) (refusal precedence); [ADR-043](ADR-043-cancellation-and-returns.md) d12.
**Amends:** BR-141 and ADR-024 d2 (cash needs every product to accept it; online needs the same); SRS §7.4's "Online or cash" rows.
**Applies first to:** `products.accepted_payment_methods`; `order_items.accepted_payment_methods_snapshot`; `POST /api/v1/checkout`; `GET /api/v1/cart`; the admin product and storefront product reads.

## Context

ADR-024 lets any all-physical order be paid in cash. The owner wants to choose, per physical product, whether it may be paid online, in cash or either: some items should only be sold against cash at the door, others only prepaid. This is a third per-product commerce setting beside Purchase Mode (checkout or WhatsApp, BR-001) and Product Type, and distinct from the per-order Payment Method and Fulfillment Method.

## Decision

1. **A new product attribute, `accepted_payment_methods`** (Q1): PostgreSQL enum `accepted_payment_methods` with values `online`, `cash`, `online_or_cash`. The glossary term is "Accepted Payment Methods". The names `online_only` and `both` were rejected because they are already Purchase Mode values with another meaning.
2. **Physical only, always set** (Q7). `ck_products_type_integrity` requires it on every physical product, WhatsApp-only ones included (so it survives a purchase-mode change), and forbids it on STL. An STL product accepts online only by rule (BR-141, ADR-024): an emailed file cannot be taken back.
3. **Default `online_or_cash`.** Admin create may omit it; the application fills the default. There is no database default, because it would also fill STL rows and break type integrity. The migration sets every existing physical product to `online_or_cash`, so today's behaviour is unchanged.
4. **The checkout rule (BR-141).** Over the lines kept after owned STLs are dropped, the methods all lines share is the intersection of each line's accepted set (STL: `{online}`). Then:
   - empty: `422 NO_COMMON_PAYMENT_METHOD`, listing every kept line's product and accepted methods, telling the customer to order them separately;
   - the chosen method not in it: `422 PAYMENT_METHOD_NOT_ALLOWED` with `reason` `cash_requires_physical` (cash with an STL line, as before), `cash_not_accepted` or `online_not_accepted`, and the refusing `product_ids`.

   It runs where `cash_requires_physical` ran (ADR-038 precedence): after `CART_EMPTY`, beside `INVALID_FULFILLMENT`, before `CART_PRICE_CHANGED` and every cash limit. Every existing cash rule and limit still applies afterwards (Q5).
5. **Snapshot on the line** (Q2). `order_items.accepted_payment_methods_snapshot` holds what the product accepted when the order was placed: set on physical lines, null on STL lines (`ck_order_items_accepted_methods_by_type`). `ck_order_items_method_accepted` requires the order's `payment_method` (already copied onto the line) to be in it. Nothing after placement reads it; it exists so the database refuses a line the rule forbids, since Ordering may not join Catalog's `products`. Existing physical lines are set to `online_or_cash`, which is what they effectively accepted.
6. **Placed orders never re-check** (Q3). The payment method is fixed on the order (BR-140): a later product change never touches retry, hold release, handover or refunds. Carts are not edited; the change applies at the next checkout.
7. **Shown, not enforced, before checkout** (Q6). Admin product create, update and read and storefront list and detail carry the field. `GET /api/v1/cart` adds `payment_methods`: the methods every line's product accepts, from products alone (not the customer's cash eligibility), empty when the cart must be split.
8. **No new lock** (Q8). Checkout reads products without locking them, as it does for price, availability and purchase mode (BR-004). An admin edit that lands during a checkout may be missed by that checkout; the snapshot records what it saw.

## Consequences

+ The owner can sell an item cash-only or prepaid-only; the default keeps every existing product and order as it was.
+ The database refuses an order line paid by a method its snapshot does not accept, as `ck_order_items_cash_is_physical` does for STL.
- A cash-only product cannot be bought by a customer who cannot pay cash: cash switched off, blocked, at the open-order limit, over `cash_max_order_total` or priced 0 (Q5). A cash-only product priced above the cap can never be sold; the admin is not warned, because the cap is a setting another context owns and can change later.
- Online-only products can be bought only once an online provider is live (§30.4, VS-032), like every online order.
- A cart holding a cash-only and an online-only product (or an STL and a cash-only product) must be split into two orders.

## Alternatives rejected

- **`cash_only` / `online_only` / `both`:** two of the three collide with Purchase Mode values.
- **An array of `payment_method`:** needs a non-empty and no-duplicates CHECK and gives the admin an ordering to get wrong; three values cover every non-empty subset.
- **No snapshot:** the rule would live only in application code, as Ordering cannot reference `products`.
- **Refusing to add a conflicting product to the cart:** a mixed cart is legitimate until checkout (ADR-029), and the customer may remove one line.
- **Locking products at checkout:** price, availability and purchase mode are not locked either; one lock for this attribute would add a lock order for no new guarantee.
