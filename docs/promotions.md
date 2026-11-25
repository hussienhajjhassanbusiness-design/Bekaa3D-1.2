# Promotions (seasonal price campaigns)

Administrator-created store or product campaigns: Eid, Ramadan, Christmas, Independence Day,
seasonal sales. A promotion is **not** an offer (a negotiation with one customer, [offers.md](offers.md))
and **not** a coupon (nothing is entered or redeemed). While it is active it lowers the price
the shop charges. The server owns the price: no client computes a discount.

Code: `app/catalog/domain/promotions.py` (rules), `app/catalog/infrastructure/promotion_repository.py`,
`app/catalog/api/promotions.py`. Migration `b7c41e2a9d10`.

## Model

`promotions`: `id`, `name`, `badge_text?`, `discount_type` (`percentage` | `fixed`),
`discount_value`, `scope` (`all` | `physical` | `stl` | `selected`), `starts_at`, `ends_at`
(exclusive), `is_active`, `created_at`, `updated_at`. `promotion_products`
(`promotion_id`, `product_id`) holds a `selected` promotion's products.

`discount_value` is a whole percent from 1 to 100 for `percentage`, and cents (USD) for `fixed`.
The database repeats the rules as CHECKs (positive value, percentage at most 100, non-blank
name and badge, `starts_at < ends_at`).

`status` is derived, never stored: `inactive` (switched off), `scheduled` (`now < starts_at`),
`ended` (`now >= ends_at`), otherwise `active`.

## The price rule

- Only an `active`-status promotion whose scope covers the product applies.
- `percentage`: the discount is `price × value / 100`, rounded half up to a cent.
- `fixed`: the discount is `value` cents.
- The effective price is never negative (a discount above the price makes it 0) and never
  above the list price. A promotion that would change nothing (1 % of 10 cents) does not apply.
- **No stacking.** When several promotions cover a product, only the one giving the lowest
  price applies; ties go to the one ending first, then the lowest id.

## Where the price is applied

| Read | Effect |
|---|---|
| `GET /api/v1/products`, `/products/{slug}` | `price` is the price charged now; `list_price` the product's own; `promotion` the one applying, or null |
| Cart (`SqlCartProductReader`) | `current_price` is the effective price; a promotion starting or ending after add-to-cart is a normal price change (`price_changed`, `409 CART_PRICE_CHANGED` at checkout until confirmed) |
| Checkout | each line is priced at the effective price |
| Orders | `order_items.unit_price_cents` snapshots the price charged; later promotion changes never touch it |
| Offers | the effective price is "today's list price": the ceiling for a counter or submission, the `minimum_offer_percentage` base, and the accept cap |
| Admin products | unchanged: `price` there is the editable list price |

Not repriced (v1): the storefront's `price_min_cents` / `price_max_cents` filters and `price`
sort use the list price; wishlist rows show the list price.

## Endpoints

| Route | Notes |
|---|---|
| `GET /api/v1/admin/promotions` | newest first, at most 200 |
| `POST /api/v1/admin/promotions` | CSRF; `201`; audited `promotion.created` |
| `GET /api/v1/admin/promotions/{id}` | |
| `PATCH /api/v1/admin/promotions/{id}` | CSRF; partial; the merged promotion is validated as a whole; `{"active": false}` switches it off; audited `promotion.updated` (no audit row for a no-op) |
| `GET /api/v1/promotions` | public, rate limited: the promotions active now, soonest ending first, without product lists |
| `GET /api/v1/products?promotion_id=` | the products an active promotion covers; an unknown or non-active one lists nothing |

Admin routes sit behind the admin boundary (administrator with MFA; a customer gets `404`).
Refusals: `422 VALIDATION_ERROR` with `errors[].loc = ["body", <field>]`, `403 CSRF_INVALID`.
There is no delete: switch a promotion off or let it end; the audit log keeps its history.
