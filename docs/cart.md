# Cart (VS-022)

The verified customer's one persistent cart, mixing physical and STL products. Decisions and rationale: [ADR-029](adr/ADR-029-cart-decisions.md). Requirements: SRS BR-020 to BR-026, §7.1, §7.2, INV-08, INV-09, F-040, F-041, FR-05. Plan: [`plans/VS-022-mixed-cart-plan.md`](plans/VS-022-mixed-cart-plan.md).

## Routes

| Method + path | Auth | Success | Errors |
|---|---|---|---|
| `GET /api/v1/cart` | Signed in (unverified allowed) | `200 CartRead` | 401 |
| `POST /api/v1/cart/items` | Verified + `X-CSRF-Token` | `200 CartRead` | 401, 403, 422 `PRODUCT_NOT_PURCHASABLE` / `QUANTITY_EXCEEDS_LIMIT` / `CART_LINE_LIMIT_REACHED` / `VALIDATION_ERROR`, 429 |
| `PATCH /api/v1/cart/items/{product_id}` | Verified + CSRF | `200 CartRead` | 401, 403, 404, 422, 429 |
| `DELETE /api/v1/cart/items/{product_id}` | Verified + CSRF | `204` | 401, 403, 404, 429 |

- `403` is `CSRF_INVALID` or `EMAIL_VERIFICATION_REQUIRED`.
- Lines are addressed by `product_id`; a cart holds at most one line per product.
- `GET` never creates a cart. A user who has never written one gets `id: null` and no items.
- `404 NOT_FOUND`: `PATCH` or `DELETE` of a product that is not in the caller's cart, including when the caller has no cart. Unlike the wishlist, `DELETE` of an absent line is a 404.
- `409 PRODUCT_ALREADY_OWNED` (`product_ids`) on `POST` for an STL the customer already owns: a paid, unrefunded line (VS-023). The customer's own unpaid order does not block the add; checkout then refuses it the same way.

## Requests

- `CartItemAdd {product_id, quantity = 1}`; `CartItemQuantityUpdate {quantity}`.
- `quantity` is a JSON integer from 1 to 2 147 483 647; `0`, negatives, strings and `1.0` are `422 VALIDATION_ERROR`. Unknown fields are refused. Use `DELETE` to remove a line.

## Adding and changing quantities

| Product | `POST` | `PATCH` (absolute) |
|---|---|---|
| STL | Quantity must be 1. Adding an STL already in the cart is a `200` no-op; `quantity: 2` is `422 QUANTITY_EXCEEDS_LIMIT` (`max_quantity: 1`). | Only `1` is accepted. |
| Physical | Merges into an existing line. The merged quantity must not exceed the product's **current** `max_quantity_per_line`; otherwise `422 QUANTITY_EXCEEDS_LIMIT` with `max_quantity`, `requested`, `current_quantity`, and the cart is unchanged. Nothing is ever clamped. | `1` to the current cap. |

- A **new** line in a cart that already has **50** lines is `422 CART_LINE_LIMIT_REACHED` (`limit: 50`); merging into an existing line still works.
- Refused products: unknown, deleted, hidden, or in an inactive or archived category give one identical `422 PRODUCT_NOT_PURCHASABLE` with `reason: "not_listed"`. Unavailable gives `reason: "unavailable"`, WhatsApp-only `reason: "whatsapp_only"`. These are the same rules as the product page's `can_add_to_cart` ([ADR-022](adr/ADR-022-storefront-commerce-capabilities.md)); the cart is never looser.

## `CartRead`

`{id, items[], contains_physical, contains_digital, payment_methods, updated_at}`. Items are in the order they were first added. `payment_methods` lists `online` / `cash` that every line's product accepts (an STL accepts online only; VS-049, [ADR-048](adr/ADR-048-accepted-payment-methods-per-product.md)); `[]` means the lines must be ordered separately, and an empty cart shows both. It reads products only, not the customer's cash eligibility. Each line:

| Field | Meaning |
|---|---|
| `product_id`, `product_type`, `name`, `quantity` | Always present. |
| `slug`, `cover_image`, `current_price` | `null` when the product is no longer listed (deleted, hidden, category off). |
| `snapshot_price` | `{amount_cents, currency}` when the line was first added. **Display only**: checkout charges the live price. Kept on merges and `PATCH`; `DELETE` then re-add takes today's price. |
| `price_changed` | The product is listed and `current_price` differs from `snapshot_price`, either way. Checkout refuses an unconfirmed change (`409 CART_PRICE_CHANGED`, VS-023). |
| `max_quantity` | The product's current per-line cap; `null` for STL and for a line that is not listed. |
| `over_cap` | The line's quantity is above the product's **current** cap (the administrator lowered it). `PATCH` can lower it; checkout refuses the line. |
| `purchasable`, `unpurchasable_reason` | `false` plus `not_listed`, `unavailable` or `whatsapp_only` when the product can no longer be bought. The line stays; `PATCH` is refused, `DELETE` works, and checkout refuses it. |

There is no total: checkout recomputes it from live prices.

## Checkout contract (built in VS-023, [`checkout.md`](checkout.md))

- Checkout locks the cart (`lock_cart_for_checkout`), revalidates every line against live Catalog state and the current caps, charges live prices, and clears the cart (`clear_cart`) in the same transaction.
- **No silent drops.** Any `not_listed`, `unavailable`, `whatsapp_only` or `over_cap` line makes checkout answer 422 naming every offending line. The only exception is SRS §7.3 step 5: an STL bought since it was added is dropped from the order, and the response names it.

## Rate limit

One bucket of **300 writes per hour per user** for `POST`, `PATCH` and `DELETE` (`RateLimit-*` headers; `429 RATE_LIMITED` with `Retry-After`). An unverified or anonymous caller never consumes it. `GET` is not limited.

## Concurrency

Every write takes the cart row lock first: `INSERT … ON CONFLICT (user_id) DO NOTHING` on a first add, then `SELECT … FROM carts WHERE user_id = :uid FOR UPDATE`. Two first adds both succeed into one cart; two `+3` adds against a cap of 5 leave one line of 3 and one 422; the 50th line goes to exactly one racer (`tests/concurrency/test_cart_races.py`). The lock order for checkout and cancellations is in ADR-029 decision 4.

## Database

`carts` (one per user, `UNIQUE (user_id)`, `ON DELETE CASCADE` from `users`) and `cart_items` (`UNIQUE (cart_id, product_id)`; `CHECK (product_type <> 'stl' OR quantity = 1)`; composite FK `(product_id, product_type) → products (id, type)`; quantity above 0; non-negative USD snapshot). Migration `bde6135b2538`.
