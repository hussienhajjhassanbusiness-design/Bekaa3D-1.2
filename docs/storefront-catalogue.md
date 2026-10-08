# Public catalogue (storefront)

The visitor-facing product list, search, autocomplete and product page,
introduced by VS-015 and VS-016. Public, unauthenticated and read-only. Admin
product management is in [products.md](products.md), and images in
[product-images.md](product-images.md).

```
GET /api/v1/products              ProductPage           422 VALIDATION_ERROR, 429 RATE_LIMITED
GET /api/v1/products/{slug}       ProductDetail         404 NOT_FOUND, 429 RATE_LIMITED
GET /api/v1/search/suggestions    SearchSuggestionList  422 VALIDATION_ERROR, 429 RATE_LIMITED
```

## Visibility

A product is on the storefront only when **all** of these hold (SRS §6.5):

- it is not soft-deleted (`deleted_at IS NULL`);
- `is_visible` is true;
- its category is live: not archived and `is_active`.

Anything else is absent from the list, and its slug answers `404 NOT_FOUND`,
the same answer as a slug that never existed. **Unavailable products stay
visible** (BR-009). They are listed and served with `is_available: false` and
`capabilities.can_add_to_cart: false`. A disabled (not archived) material or
colour doesn't hide a product. It still shows on the product, but it isn't
offered as a facet by `GET /materials` / `GET /colours`. Archived values can't
be on a live product (VS-013 in-use guard).

## List: `GET /api/v1/products`

| Parameter | Meaning |
| --- | --- |
| `type` | `physical` or `stl` (F-004, F-005); omitted lists both |
| `category_id`, `material_id`, `colour_id` | exact match. STL products have no material or colour, so those facets only return physical ones |
| `price_min_cents`, `price_max_cents` | inclusive, integer cents, 0 to 2⁶³−1; min > max is a 422 |
| `min_rating` | decimal 0 to 5 with at most 2 decimal places (the column's precision), `average_rating >= min_rating` |
| `featured` | `true` only featured, `false` only non-featured |
| `q` | search names and descriptions (see [Search](#search)); trimmed, blank means no search, at most 200 characters |
| `sort` | `-created_at` (default), `price`, `-price`, `-average_rating`; with `q`, also `-relevance` (the default then); anything else is a 422 |
| `cursor`, `limit` | opaque cursor from `next_cursor`; `limit` 1 to 100, default 20 |

Facets combine with AND, and with `q`. Unknown query parameters are ignored
(the house convention). A bad value is
`422 VALIDATION_ERROR` with the parameter in `errors[].loc`, for example
`["query", "cursor"]`. api-endpoints.md §7.1 used to say 400. The project-wide
convention, and that document's own error table, is 422.

### Cursor

Keyset pagination on `(sort key, id)`. `id` always breaks ties, in the same
direction as the sort. The cursor is opaque and bound to its sort: reusing it
under another sort, or altering it, is a 422. That includes a key outside what its
column can hold (a price outside 0 to 2⁶³−1, a rating outside 0 to 5 or finer than
0.01), so a forged cursor never reaches PostgreSQL.

**Guarantee:** inserts, deletions and hides between page fetches never make an
already-existing product repeat or vanish. A new product shows up on later
pages only if it sorts after the cursor
(`tests/concurrency/test_storefront_cursor_under_inserts.py`).
**Limit (accepted):** if a product's own sort key changes while someone is
browsing (an administrator edits its price, or a review moves its rating), it
can cross the cursor and be seen twice or not at all. Avoiding that would need
snapshot reads across requests, which keyset cursors don't give.

## Search

ADR-023 has the rationale. `q` runs in two modes, chosen on the first page and
pinned in the cursor:

- **Full text** (the normal case): `search_vector @@ websearch_to_tsquery('english', q)`.
  Snowball stemming means `dragons` and `Dragon` both find "Articulated Dragon".
  `websearch_to_tsquery` never raises on syntax, so quotes, `-` and operators
  are just text to it.
- **Fuzzy** (when fewer than **5** full-text hits match the facets): full-text
  hits **or** names with `word_similarity(q, name) >= 0.5`. That threshold finds
  one deleted, substituted or inserted letter (`dragn`, `dragom`, `plnter`). A
  transposition (`dargon`) is out of reach for trigrams.

With `q`, the default order is `-relevance`: `1 + ts_rank` for a full-text hit
(name, weight A, above description, weight B), else the name's
`word_similarity`. Every full-text hit therefore comes before every
trigram-only one. Explicit sorts still work with `q`.

**Cursor.** A search cursor carries its mode, so a walk that started in fuzzy
mode stays in fuzzy mode even if new products lift the full-text count past five
(`tests/concurrency/test_storefront_search_cursor.py`). A search cursor without
`q`, or a browse cursor with `q`, is a 422. The cursor isn't bound to the `q`
text itself.

**Safety (SEC-24).** The term is always a bound parameter. The `<%` threshold is
set with `set_config(..., true)`, which is transaction-local, so it never leaks
to the next request on a pooled connection. Control characters are refused by
the request middleware with 422.

## Autocomplete: `GET /api/v1/search/suggestions`

| Parameter | Meaning |
| --- | --- |
| `q` | required; trimmed; 2 to 200 characters |
| `limit` | 1 to 10, default 10 |

It returns `{"items": [{"id", "name", "slug", "type"}]}`, visible products only,
whose name passes the same trigram test as fuzzy search, closest first (then
name, then `id`). It suits type-ahead: `drag` already suggests "Articulated
Dragon".

## Payloads

`ProductListItem` (api-endpoints.md §30): `id`, `type`, `name`, `slug`,
`cover_image` (`{id, url, alt_text, is_cover}` or null), `price`
(`{amount_cents, currency}`), `category` (`{id, name, slug}`), `material` /
`colour` (`{id, name}` or null), `is_available`, `purchase_mode` (null for STL),
`average_rating`, `review_count`, `is_featured`.

`ProductDetail` adds `description`, `images` (every live image, in display
order), `seo_title`, `seo_description`, `og_image_url`, `dimensions`,
`production_lead_time_days`, `batch_size`, `max_quantity_per_line` and
`capabilities`.

Never exposed: `is_visible`, `version`, `wishlist_count`, `weight_grams`
(reserved for future shipping), `deleted_at` and timestamps. Tests pin the exact
key sets.

### Capabilities (ADR-022)

| Flag | True when |
| --- | --- |
| `can_add_to_cart` | available AND (STL, or `purchase_mode` is `online_only`/`both`) |
| `can_offer` | STL AND available |
| `whatsapp_available` | physical AND `purchase_mode` is `whatsapp_only`/`both` (availability doesn't matter) |

These are product-level hints. The cart and checkout re-check everything,
including STL ownership, which this anonymous endpoint can't know. STL pages
carry no delivery-promise field: the description says what the customer
receives, and the delivery-time text waits for SRS §30.2.

## Slugs

Lookup is exact against the stored, canonical slug. An uppercase or otherwise
non-canonical slug, or an old slug after a rename, is `404` (no redirects in
V1). A slug carrying control characters is refused earlier, by the request
middleware, with 422.

## Rate limits

600 requests per hour per client IP, with a separate counter for the list, the
detail and the suggestions route. This is the VS-010 public allowance. Behind the future
reverse proxy every client would share one IP, and VS-020 owns that fix.

## Performance (NFR-01, NFR-07)

The SRS §21.3 partial indexes (`ix_products_browse_*`, all
`WHERE deleted_at IS NULL AND is_visible`) were created by VS-013. The query
writes the visibility predicate as bare `is_visible`, not `IS TRUE`, so the
planner can match those partial indexes. After a cursor, it adds a redundant
single-column bound (`price_cents >= key`) that an index can seek on.
`tests/integration/catalog/test_storefront_scale.py` seeds 10,000 products. It
asserts that each browse shape's plan uses its index, and that p95 latency
through the HTTP stack stays under 500 ms. For search (NFR-02), it asserts that
full-text plans use `ix_products_search_vector`, that fuzzy search and
suggestions use `ix_products_name_trgm`, and that p95 stays under 800 ms. The
seed is `VACUUM`ed, as autovacuum would be, because a bulk insert leaves rows in
the GIN pending list, and the planner then won't use the index.
