# 02 — Catalog

The public storefront and the administrator's catalogue: products, categories, materials, colours
and product images. Requirements: FR-01, FR-04; BR-001 to BR-019; ADR-016, ADR-020 to ADR-023,
ADR-048.

Code: routers in `src/app/catalog/api/`, use cases in `src/app/catalog/application/commands/`,
rules in `src/app/catalog/domain/` (`product.py`, `storefront.py`, `product_image.py`),
queries in `src/app/catalog/infrastructure/` (`storefront_query.py`, `repositories.py`).

Who-can-call labels: see [01-identity.md](01-identity.md). Seeded data: [00-overview.md §4.2](00-overview.md#42-seed-data-and-the-credentials-file).

**Visibility rule** (SRS §6.5): a product is on the storefront only when it is not deleted,
`is_visible` is true and its category is live (not archived and active). Anything else answers
`404` by slug, exactly like a slug that never existed. An **unavailable** product stays listed
(BR-009) with `is_available: false` and `capabilities.can_add_to_cart: false`.

---

## Public storefront

All public reads are limited to 600 per hour per IP (`429 RATE_LIMITED`), except suggestions
(3000 per hour).

### `GET /api/v1/products`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Anonymous | no | no | 600 per hour per IP |

Lists visible products with facets, search and keyset paging.

| Parameter | Meaning |
| --- | --- |
| `type` | `physical` or `stl` |
| `category_id`, `material_id`, `colour_id` | exact match (STL products have no material or colour) |
| `price_min_cents`, `price_max_cents` | inclusive; min > max is `422` |
| `min_rating` | 0 to 5, at most 2 decimals |
| `featured` | `true` / `false` |
| `q` | full-text search of name and description (≤ 200 characters, trimmed; blank = no search). Fewer than 5 full-text hits switches to typo-tolerant name matching |
| `sort` | `-created_at` (default), `price`, `-price`, `-average_rating`; `-relevance` only with `q` (its default then) |
| `cursor`, `limit` | opaque cursor bound to its sort; `limit` 1-100, default 20 |

Response `200` (one item shown):

```json
{
  "items": [
    {
      "id": "0c5e…",
      "type": "physical",
      "name": "Articulated Dragon",
      "slug": "dragon",
      "cover_image": {"id": "…", "url": "/media/products/….png", "alt_text": null, "is_cover": true},
      "price": {"amount_cents": 1800, "currency": "USD"},
      "category": {"id": "…", "name": "Toys and Figures", "slug": "toys-figures"},
      "material": {"id": "…", "name": "PLA"},
      "colour": {"id": "…", "name": "Red"},
      "is_available": true,
      "purchase_mode": "both",
      "accepted_payment_methods": "online_or_cash",
      "average_rating": 0.0,
      "review_count": 0,
      "is_featured": false
    }
  ],
  "next_cursor": "eyJ…"
}
```

| Status | Code | When |
| --- | --- | --- |
| 422 | `VALIDATION_ERROR` | unknown `type`/`sort`, min > max, `-relevance` without `q`, bad or tampered cursor, a cursor reused under another sort, `limit` 0 or 101 |
| 429 | `RATE_LIMITED` | over 600 per hour |

Code: `catalog/api/storefront.py` (`list_products`), `domain/storefront.py`,
`infrastructure/storefront_query.py`.

### `GET /api/v1/products/{slug}`

Anonymous; 600 per hour. Returns one visible product with all live images and `capabilities`:

- `can_add_to_cart`: available, and STL or a physical `online_only`/`both` product;
- `can_offer`: available STL;
- `whatsapp_available`: physical `whatsapp_only`/`both`.

Response `200` adds to the list item: `description`, `images[]`, `seo_title`, `seo_description`,
`og_image_url`, `dimensions`, `production_lead_time_days`, `batch_size`, `max_quantity_per_line`,
`capabilities` (`{"can_add_to_cart": true, "can_offer": false, "whatsapp_available": true}`).

Errors: `404 NOT_FOUND` (no visible product with that slug, or a non-canonical slug such as
upper case), `429`. Code: `catalog/api/storefront.py` (`read_product`).

### `GET /api/v1/search/suggestions`

Anonymous; 3000 per hour. Typo-tolerant name suggestions for autocomplete. Query: `q` (needs a
word of at least 3 letters or digits), `limit` 1-10 (default 10).

Response `200`: `{"items": [{"id": "…", "name": "Articulated Dragon", "slug": "dragon", "type": "physical"}]}`.

Errors: `422 VALIDATION_ERROR` (no 3-character word, `limit` out of range), `429`.
Code: `catalog/api/search.py`, `domain/storefront.py` (`suggestion_term_errors`).

### `GET /api/v1/categories`, `GET /api/v1/materials`, `GET /api/v1/colours`

Anonymous; 600 per hour each. Only live, active values, ordered by name, at most 100.
Responses: `{"items": [{"id", "name", "slug"}]}` for categories, `{"items": [{"id", "name"}]}`
for materials and colours. Code: `catalog/api/reference_data.py`.

| ID | Test | Expected |
| --- | --- | --- |
| CAT-01 | Anonymous `GET /products` | `200`; 9 items; no `prototype-gear` or `holiday-ornament`; `knight` and `low-poly-vase-stl` present with `is_available: false` |
| CAT-02 | `GET /products?type=stl` | only `dragon-stl`, `phone-stand-stl`, `low-poly-vase-stl` |
| CAT-03 | `GET /products?featured=true` | `moon-lamp`, `phone-stand-stl` |
| CAT-04 | `GET /products?sort=price&limit=2`, then the same with `cursor=<next_cursor>` | pages in ascending price; no product repeats |
| CAT-05 | Use page 1's cursor with `sort=-price` | `422 VALIDATION_ERROR`, `loc` `["query","cursor"]` |
| CAT-06 | `GET /products?price_min_cents=2000&price_max_cents=1000` | `422 VALIDATION_ERROR` |
| CAT-07 | `GET /products?sort=-relevance` (no `q`) | `422 VALIDATION_ERROR` on `sort` |
| CAT-08 | `GET /products?q=dragons` | both dragon products (stemming) |
| CAT-09 | `GET /products?q=dragn` | the dragon products (fuzzy fallback) |
| CAT-10 | `GET /products/dragon` | `200`; two images; `capabilities.can_add_to_cart: true`, `whatsapp_available: true` |
| CAT-11 | `GET /products/name-sign` | `can_add_to_cart: false`, `whatsapp_available: true` (WhatsApp only) |
| CAT-12 | `GET /products/dragon-stl` | `can_offer: true`, `whatsapp_available: false` |
| CAT-13 | `GET /products/prototype-gear` and `/products/holiday-ornament` | both `404 NOT_FOUND` |
| CAT-14 | `GET /products/Dragon` | `404 NOT_FOUND` |
| CAT-15 | `GET /search/suggestions?q=drag` | dragon products |
| CAT-16 | `GET /search/suggestions?q=dr` | `422 VALIDATION_ERROR` on `q` |
| CAT-17 | `GET /categories` | three categories; no `seasonal` |
| CAT-18 | `GET /products/` (trailing slash) | `307` redirect |

---

## Admin: categories, materials, colours

Under the admin boundary. Each value has three states: **live** (active), **disabled**
(`is_active: false`: hidden publicly, still assignable, re-activatable) and **archived**
(`DELETE` sets `deleted_at`: terminal, its slug or name is freed). Categories have a `slug`
(`^[a-z0-9]+(-[a-z0-9]+)*$`, ≤ 200, lower-cased); materials and colours have unique names,
ignoring case. Every write is audited. BR-011 to BR-013.

Code: `catalog/api/reference_data.py`, `catalog/api/schemas.py`,
`application/commands/category_admin.py`, `application/commands/value_admin.py`,
`domain/entities.py`.

| Method and path | Who | CSRF | Body | Success |
| --- | --- | --- | --- | --- |
| `GET /api/v1/admin/categories` | Admin | no | query `cursor`, `limit` (1-100, 20), `include_deleted` | `200 {items, next_cursor}` |
| `POST /api/v1/admin/categories` | Admin | yes | `{name, slug, is_active?}` | `201 CategoryDetail` |
| `GET /api/v1/admin/categories/{category_id}` | Admin | no | | `200 CategoryDetail` (archived too) |
| `PATCH /api/v1/admin/categories/{category_id}` | Admin | yes | any of `{name, slug, is_active}` | `200 CategoryDetail` |
| `DELETE /api/v1/admin/categories/{category_id}` | Admin | yes | | `204` (archive) |
| `GET/POST /api/v1/admin/materials`, `GET/PATCH/DELETE /api/v1/admin/materials/{material_id}` | Admin | writes | `{name, is_active?}` | as above |
| `GET/POST /api/v1/admin/colours`, `GET/PATCH/DELETE /api/v1/admin/colours/{colour_id}` | Admin | writes | `{name, is_active?}` | as above |

Request: `{"name": "Lamps", "slug": "lamps", "is_active": true}`.
Response `201`:

```json
{
  "id": "9b2c…",
  "name": "Lamps",
  "slug": "lamps",
  "is_active": true,
  "deleted_at": null,
  "created_at": "2026-11-07T10:00:00Z",
  "updated_at": "2026-11-07T10:00:00Z"
}
```

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown id; caller is a customer |
| 409 | `SLUG_CONFLICT` | a live category has the slug, or a live material/colour has the name in any case |
| 409 | `INVALID_STATE_TRANSITION` | `PATCH` or `DELETE` of an archived value |
| 409 | `CATEGORY_IN_USE` | archiving a category, material or colour that a live product uses (one code for all three) |
| 422 | `VALIDATION_ERROR` | bad slug (`"Desk Lamps"`, `-lamps`, `a--b`), blank or invisible-only name, over 200 characters, unknown field |

| ID | Test | Expected |
| --- | --- | --- |
| CAT-19 | Create category `{"name": "Lamps", "slug": "lamps"}` | `201`; audit row; appears in public `GET /categories` |
| CAT-20 | Create another with slug `lamps` | `409 SLUG_CONFLICT` |
| CAT-21 | Create with slug `Desk Lamps` | `422 VALIDATION_ERROR` on `slug` |
| CAT-22 | `PATCH` it `{"is_active": false}` | `200`; gone from public `/categories` |
| CAT-23 | `DELETE` it (no products) | `204`; then `PATCH` it → `409 INVALID_STATE_TRANSITION`; creating a new `lamps` now works |
| CAT-24 | `DELETE` the `toys-figures` category | `409 CATEGORY_IN_USE` |
| CAT-25 | Create material `pla` | `409 SLUG_CONFLICT` (PLA exists, case-insensitive) |
| CAT-26 | `GET /admin/categories?include_deleted=true` | archived categories listed with `deleted_at` set |
| CAT-27 | As the customer, `POST /admin/categories` | `404 NOT_FOUND` |
| CAT-28 | As the admin, `POST /admin/colours` without the CSRF header | `403 CSRF_INVALID` |

---

## Admin: products

Physical and STL products in one table. Requirement FR-04, F-111; ADR-020 (optimistic
versioning), ADR-048 (accepted payment methods).

Code: `catalog/api/products.py`, `api/product_schemas.py`,
`application/commands/product_admin.py`, `domain/product.py`,
`infrastructure/product_repository.py`.

Rules:

- `price` is `{"amount_cents": int ≥ 0, "currency": "USD"}`.
- **Physical** needs `purchase_mode`, `production_lead_time_days` (≥ 0), `batch_size` (> 0) and
  `max_quantity_per_line` (> 0); `accepted_payment_methods` defaults to `online_or_cash`.
  `material_id`, `colour_id`, `dimensions`, `weight_grams` are optional.
- **STL** must leave every physical-only field null (`purchase_mode`, `accepted_payment_methods`,
  `material_id`, `colour_id`, `dimensions`, lead time, batch size, max quantity, weight).
- `type` cannot change. `is_visible` defaults to `false`.
- Every write sends back the `version` it read; a stale one is `409 VERSION_CONFLICT` with
  `current_version`. `DELETE` takes `?version=N`. Delete is soft and terminal.
- A disabled category, material or colour can be assigned; an archived or unknown one is `422`.

| Method and path | Who | CSRF | Success |
| --- | --- | --- | --- |
| `GET /api/v1/admin/products` | Admin | no | `200 AdminProductPage`; filters `type`, `category_id`, `is_visible`, `is_featured`, `is_available`, `deleted`, `q` (1-200), `sort` (`-created_at`, `price`, `-price`), `cursor`, `limit` |
| `POST /api/v1/admin/products` | Admin | yes | `201 AdminProductDetail` |
| `GET /api/v1/admin/products/{product_id}` | Admin | no | `200 AdminProductDetail` (deleted too) |
| `PATCH /api/v1/admin/products/{product_id}` | Admin | yes | `200 AdminProductDetail` |
| `DELETE /api/v1/admin/products/{product_id}?version=N` | Admin | yes | `204` |

Create request (physical):

```json
{
  "type": "physical",
  "category_id": "<home-decor id>",
  "name": "Desk Lamp",
  "slug": "desk-lamp",
  "description": "A small printed lamp.",
  "price": {"amount_cents": 2500, "currency": "USD"},
  "is_visible": true,
  "purchase_mode": "both",
  "accepted_payment_methods": "online_or_cash",
  "production_lead_time_days": 3,
  "batch_size": 2,
  "max_quantity_per_line": 5,
  "dimensions": {"length_mm": 120, "width_mm": 120, "height_mm": 200}
}
```

Response `201` (abridged): `{"id": "…", "type": "physical", "name": "Desk Lamp", "slug": "desk-lamp",
"price": {"amount_cents": 2500, "currency": "USD"}, "is_visible": true, "is_featured": false,
"is_available": true, "purchase_mode": "both", "accepted_payment_methods": "online_or_cash", …,
"average_rating": 0.0, "review_count": 0, "wishlist_count": 0, "version": 1, "deleted_at": null,
"images": []}`.

Update request: `{"version": 1, "price": {"amount_cents": 2700, "currency": "USD"}}`.

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown id |
| 409 | `SLUG_CONFLICT` | a live product has the slug |
| 409 | `VERSION_CONFLICT` | stale `version`; body has `current_version` |
| 409 | `INVALID_STATE_TRANSITION` | `PATCH`/`DELETE` of a deleted product |
| 422 | `VALIDATION_ERROR` | type integrity (an STL with `batch_size`, a physical without `purchase_mode`), archived or unknown category/material/colour, `currency` not USD, negative price, `type` in an update, a server field (`average_rating`, `id`) in the body, missing `version` |

| ID | Test | Expected |
| --- | --- | --- |
| CAT-29 | Create the physical product above | `201`, `version: 1`; visible at `GET /products/desk-lamp`; audit `product.created` |
| CAT-30 | Create an STL with `"batch_size": 1` | `422 VALIDATION_ERROR` naming `batch_size` |
| CAT-31 | Create a physical product without `purchase_mode` | `422 VALIDATION_ERROR` |
| CAT-32 | Create with `"price": {"amount_cents": 100, "currency": "EUR"}` | `422 VALIDATION_ERROR` |
| CAT-33 | `PATCH` with `version: 1` and a new price | `200`, `version: 2` |
| CAT-34 | `PATCH` again with `version: 1` | `409 VERSION_CONFLICT`, `current_version: 2`; nothing written |
| CAT-35 | `PATCH` `{"version": 2, "type": "stl"}` | `422 VALIDATION_ERROR` |
| CAT-36 | `PATCH` `{"version": 2, "is_available": false}` | storefront shows `is_available: false`, `can_add_to_cart: false` |
| CAT-37 | `PATCH` `{"version": 3, "purchase_mode": "whatsapp_only"}` | storefront `can_add_to_cart: false`; a cart holding it is refused at checkout (see ORD tests) |
| CAT-38 | `DELETE ?version=1` (stale) | `409 VERSION_CONFLICT` |
| CAT-39 | `DELETE` with the current version | `204`; `GET /products/desk-lamp` → `404`; admin `GET` still shows it with `deleted_at` |
| CAT-40 | Create another product with slug `desk-lamp` | `201` (the deleted one freed the slug) |
| CAT-41 | `GET /admin/products?deleted=true` | only deleted products |

---

## Admin: product images

Under `/api/v1/admin/products/{product_id}/images`. ADR-021. The upload is scanned (ClamAV),
type-sniffed (JPEG, PNG, WebP only), decoded (≤ 40 MP) and re-encoded, so metadata never
survives. At most 20 live images per product; the first image becomes the cover. Image changes do
not change the product's `version`.

Code: `catalog/api/product_images.py`, `api/product_image_schemas.py`,
`application/commands/product_image_admin.py`, `domain/product_image.py`,
`integrations/scanning/`, `integrations/images/`, `integrations/storage/`.

| Method and path | Who | CSRF | Body | Success |
| --- | --- | --- | --- | --- |
| `POST …/images` | Admin | yes | multipart: `file` (≤ 10 MB), `alt_text?` (≤ 300) | `201 ProductImageRead` |
| `PATCH …/images/{image_id}` | Admin | yes | `{"alt_text": "…" \| null}` | `200 ProductImageRead` |
| `PUT …/images/order` | Admin | yes | `{"image_ids": [every live id, once]}` | `200 {items}` |
| `PUT …/images/{image_id}/cover` | Admin | yes | none | `200 ProductImageRead` |
| `DELETE …/images/{image_id}` | Admin | yes | none | `204` (soft; file kept) |

Response `201`:

```json
{
  "id": "e1a4…",
  "product_id": "…",
  "url": "/media/products/7c1d….png",
  "alt_text": "Lamp, front view",
  "sort_order": 0,
  "is_cover": true,
  "created_at": "2026-11-07T10:00:00Z",
  "updated_at": "2026-11-07T10:00:00Z"
}
```

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown product, or the image is not a live image of this product |
| 409 | `INVALID_STATE_TRANSITION` | the product is deleted; deleting the cover while other images remain |
| 422 | `UPLOAD_REJECTED` | over 10 MB (or a missing/too large `Content-Length`), empty, not JPEG/PNG/WebP, undecodable, over 40 MP, or the 21st image |
| 422 | `MALWARE_DETECTED` | ClamAV flagged the file |
| 422 | `VALIDATION_ERROR` | `image_ids` missing an image, with a duplicate, a foreign or deleted id; control characters in `alt_text` |
| 503 | `SERVICE_UNAVAILABLE` | ClamAV unreachable (fail closed) |

| ID | Test | Expected |
| --- | --- | --- |
| CAT-42 | Upload a small PNG to the CAT-40 product | `201`, `is_cover: true`, `sort_order: 0`; it shows as `cover_image` on the storefront |
| CAT-43 | Upload a second image | `201`, `is_cover: false`, `sort_order: 1` |
| CAT-44 | `PUT …/{second}/cover` | `200`; the first is no longer cover |
| CAT-45 | `PUT …/order` with the two ids reversed | `200`, `sort_order` 0 and 1 swapped |
| CAT-46 | `PUT …/order` with only one id | `422 VALIDATION_ERROR` |
| CAT-47 | `DELETE` the cover while the other image is live | `409 INVALID_STATE_TRANSITION` |
| CAT-48 | Upload a `.txt` file renamed to `.png` | `422 UPLOAD_REJECTED` |
| CAT-49 | Upload the EICAR test string saved as a file | `422 MALWARE_DETECTED` (needs ClamAV healthy) |
| CAT-50 | `PATCH …/{id}` with `{"alt_text": null}` | `200`, `alt_text: null` |
| CAT-51 | Upload with `docker compose stop clamav` | `503 SERVICE_UNAVAILABLE`; restart ClamAV afterwards |
