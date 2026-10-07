# Products (admin)

The administrator's product catalogue: physical and STL products in one table,
created and maintained through `/api/v1/admin/products`. Introduced by VS-013.
The public catalogue (VS-015), images (VS-014), search (VS-016) and the
aggregates' writers (reviews VS-036, wishlist VS-038) build on it.

## The table

`products` follows `database-design.md` §6.4, plus one addition: `version`
(ADR-020). Migration `fc18b48a1780`.

| Group | Columns |
| --- | --- |
| Common | `id`, `type` (`product_type`: `physical`/`stl`), `category_id`, `name`, `description`, `slug`, `seo_title`, `seo_description`, `og_image_url`, `price_cents` + `currency`, `is_visible` (default false), `is_featured` (default false), `is_available` (default true) |
| Physical only | `purchase_mode` (`online_only`/`whatsapp_only`/`both`), `material_id`, `colour_id`, `dimensions`, `production_lead_time_days`, `batch_size`, `max_quantity_per_line`, `weight_grams` |
| Server-maintained | `search_vector` (generated), `average_rating`, `review_count`, `wishlist_count`, `version` |
| Lifecycle | `deleted_at`, `created_at`, `updated_at` |

There is no `stock_quantity` (BR-005) and no `download_count` (ADR-019).

### Database constraints

Every rule below is enforced by PostgreSQL. `tests/integration/catalog/test_product_schema.py`
proves each one through raw SQL.

| Constraint | Rule |
| --- | --- |
| `ck_products_type_integrity` | physical ⇒ `purchase_mode`, `production_lead_time_days`, `batch_size`, `max_quantity_per_line` NOT NULL; STL ⇒ all eight physical-only columns NULL (SRS §6.2) |
| `ck_products_price_non_negative`, `ck_products_currency_usd` | integer cents ≥ 0, currency `USD` (ADR-008) |
| `ck_products_name_not_blank` | BR-017 / INV-12 |
| `ck_products_slug_format` | `^[a-z0-9]+(-[a-z0-9]+)*$`, the same rule as category slugs, so no case-variant index is needed |
| `ix_products_live_slug` | `UNIQUE(slug) WHERE deleted_at IS NULL` (INV-13); soft delete releases the slug |
| `ck_products_lead_time_non_negative` | lead time ≥ 0 (a same-day item is allowed) |
| `ck_products_batch_size_positive`, `ck_products_max_quantity_positive`, `ck_products_weight_positive` | > 0 when present |
| `ck_products_dimensions_shape` | `dimensions`, when present, is an object with exactly `length_mm`, `width_mm`, `height_mm`, each a positive integer |
| `ck_products_rating_range`, `…_review_count_non_negative`, `…_wishlist_count_non_negative` | aggregate sanity |
| `ck_products_version_positive` | `version ≥ 1` |
| FKs to `categories`, `materials`, `colours` | `ON DELETE RESTRICT` |

Indexes: the live-slug index; GIN on `search_vector` and on `name gin_trgm_ops`
(§18.2); the four §19.1 storefront indexes, created now so VS-015 needs no
migration; and partial indexes on `category_id`, `material_id` and `colour_id`
for the in-use check.

`search_vector` is `GENERATED ALWAYS … STORED`: `english` config, name weighted
`A`, description `B` (SRS §6.3).

## Decisions made in VS-013

- **Availability applies to both types** (owner decision, 2026-10-07). With
  manual STL delivery (ADR-019) the administrator must be able to pause STL
  sales. SRS §6.1 was updated in the same PR. Before that it listed the
  availability toggle under "physical only", while BR-009, INV-07, the
  glossary, the DB design and the API schema already treated it as common.
- **Material and colour are optional on a physical product.**
  `entities-and-business-rules.md` says they are "required for physical
  products"; `database-design.md` §6.4 says to keep them nullable unless the
  requirement is tightened; the SRS doesn't say. Kept nullable. **This is an open
  conflict between the two supporting documents.** Tightening it later needs
  a CHECK and a data fix.
- **Lead time ≥ 0.** `entities-and-business-rules.md` says lead time, batch
  size and max quantity must be *positive*; `database-design.md` says lead time
  ≥ 0. The frozen DB design wins for lead time. Batch size and max quantity are
  > 0 in both.
- **`dimensions`** is `{length_mm, width_mm, height_mm}`, all required, all
  positive integers. No document specified a shape.
- **Disabled values can be assigned.** A product may reference a category,
  material or colour that is disabled (`is_active = false`) but not one that is
  archived, so an administrator can prepare products before the value goes
  live. An archived or unknown value is `422 VALIDATION_ERROR` on its field.
- **Soft delete leaves visibility alone.** Deleting sets only `deleted_at`;
  `is_visible` and `is_available` keep their values, because visibility,
  availability and deletion are separate concepts (entities doc, Product).
  Storefront queries exclude deleted rows whatever their flags. A deleted
  product is terminal: PATCH or DELETE answers `409 INVALID_STATE_TRANSITION`.
  There is no restore endpoint.
- **Edge limits** (V1 choices; the columns are unbounded TEXT): name, slug and
  SEO title ≤ 200 characters; SEO description ≤ 500; description ≤ 10,000 (line
  breaks allowed, other control characters refused); `og_image_url` an
  `http(s)` URL ≤ 2,000. Integer fields are capped at the PostgreSQL type's
  maximum, so an oversized value is a 422, not a database error.

## Endpoints

All are under the `/api/v1/admin` boundary (SEC-10: anonymous `401`, customer
`404`), and the unsafe methods require CSRF.

```
GET    /api/v1/admin/products            AdminProductPage
POST   /api/v1/admin/products            201 AdminProductDetail  409 SLUG_CONFLICT, 422
GET    /api/v1/admin/products/{id}       AdminProductDetail      includes deleted
PATCH  /api/v1/admin/products/{id}       AdminProductDetail      409 SLUG_CONFLICT / VERSION_CONFLICT /
                                                                 INVALID_STATE_TRANSITION, 422
DELETE /api/v1/admin/products/{id}?version=N   204               409 VERSION_CONFLICT /
                                                                 INVALID_STATE_TRANSITION, 422
```

**Create** takes `AdminProductCreate` (api-endpoints.md §29.10). `price` is
`{amount_cents, currency}` with integer cents and currency `USD` only. Unknown
fields are refused, so `average_rating`, `review_count`, `wishlist_count`, `id`
or `version` in a body is a 422.

**Update** takes the same fields, all optional, plus a required `version`.
`type` is immutable and refused. A field set to `null` is cleared. A field
left out is untouched. `name`, `slug`, `price`, `category_id` and the three
flags cannot be null. Type integrity is checked on the *merged* state, so
adding a lead time to an STL product, or clearing `batch_size` on a physical
one, is a 422 naming the field.

**Delete** is a soft delete and needs `?version=N`. A missing or invalid
version is a 422.

**List** filters: `type`, `category_id`, `is_visible`, `is_featured`,
`is_available`, `deleted` (`true` lists only deleted products; the default is
live only), and `q`. `q` matches English full-text on name and description, or
a case-insensitive substring of the name. Sorts: `-created_at` (default),
`price`, `-price`, always tie-broken by `id`. The cursor is opaque and bound to
its sort; using it with another sort is a 422. Unknown query parameters are
ignored, following the existing convention (see the VS-012 follow-up in the
slice plan).

Reads return every column except `search_vector`, including `version`.
Reads also carry `images`, the live ones in display order (VS-014, [product-images.md](product-images.md)).

## Optimistic concurrency

ADR-020: every read returns `version`, and every write must send it back.

```
409 VERSION_CONFLICT
{ "code": "VERSION_CONFLICT", "current_version": 7, ... }
```

Nothing is written on a conflict, not even an audit row. Only
administrator-editable fields bump the version. Aggregate maintenance and no-op
PATCHes don't.

## Referenced values and archiving

See [reference-data.md](reference-data.md#the-in-use-archive-guard-vs-013).
Product writes share-lock each newly referenced category, material or colour.
Archiving one that a live product uses is `409 CATEGORY_IN_USE`.

## Audit

Every successful write records one row in the same transaction:
`product.created` (no before), `product.updated` (also for a no-op, with equal
before and after) and `product.deleted`. `entity_type` is `Product`. Snapshots
hold `type`, every editable field, `version` and `deleted_at`, but not the
aggregates. A refused write records nothing, and a failed audit write rolls the
product change back (FR-04).
