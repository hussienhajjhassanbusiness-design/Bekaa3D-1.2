# Product images (admin)

Images the administrator uploads, orders and picks a cover from, under
`/api/v1/admin/products/{product_id}/images`. Introduced by VS-014; the public
catalogue (VS-015) reads them. The upload pipeline is ADR-021.

## The table

`product_images` follows `database-design.md` §6.5. Migration `cc87333ebe79`.

| Column | Notes |
| --- | --- |
| `id`, `product_id` | FK → `products`, `ON DELETE RESTRICT` (products are never hard-deleted) |
| `storage_key` | `products/<uuid4>.<jpg\|png\|webp>`; unique across all rows, deleted ones included |
| `alt_text` | optional, ≤ 300 characters |
| `sort_order` | ≥ 0; display order, ties broken by `created_at`, `id` |
| `is_cover` | at most one live cover per product |
| `deleted_at`, `created_at`, `updated_at` | soft delete; the file is kept |

| Constraint | Rule |
| --- | --- |
| `ix_product_images_live_cover` | `UNIQUE(product_id) WHERE is_cover AND deleted_at IS NULL` |
| `ck_product_images_deleted_not_cover` | a deleted image is never the cover |
| `ck_product_images_storage_key_format` | only generated keys, so no client name or `../` ever reaches the filesystem |
| `uq_product_images_storage_key` | two rows never share a file, which keeps the reaper's "referenced?" answer exact |
| `ck_product_images_sort_order_non_negative` | `sort_order ≥ 0` |

## Storage, scanning, re-encoding

The shared ports and adapters live in `app.integrations` (ADR-013):

- **`StoragePort` / `LocalStorage`.** Files go under `MEDIA_PUBLIC_DIR`
  (`/data/media_public`). Writes are atomic: a temporary file, then a rename.
  Keys can't escape the root. nginx serves the directory under
  `MEDIA_PUBLIC_URL` (`/media`) from VS-020. Reads return `url` =
  `MEDIA_PUBLIC_URL/storage_key`.
- **`MalwareScannerPort` / `ClamAvScanner`.** clamd's `INSTREAM` protocol over
  TCP (`CLAMAV_HOST`, `CLAMAV_PORT`). `FakeScanner` is for tests, and the
  factory refuses it outside test and development environments.
- **`ImageSanitizerPort` / `PillowImageSanitizer`.**
  - It sniffs magic bytes and accepts only JPEG, PNG and WebP.
  - It decodes at most 40 MP, applies EXIF orientation, then copies the
    pixels into a new image and encodes that: JPEG at quality 90, PNG
    optimised, WebP at quality 90.
  - EXIF, GPS, ICC, XMP, text chunks and bytes after the end marker never
    survive. The format family is kept.

## Upload pipeline (ADR-021)

1. **Size:** the request must declare a `Content-Length` no larger than 10 MB plus 64 KiB of multipart framing. That check runs after the admin boundary and *before* the body is parsed. The file itself must be 1 byte to 10 MB. Either failure → `422 UPLOAD_REJECTED`.
2. **Scan the raw bytes:**
   - infected → `422 MALWARE_DETECTED`;
   - scanner unavailable → `503 SERVICE_UNAVAILABLE` (fail closed).
3. **Type by content, then a bounded decode and re-encode.** Anything else →
   `422 UPLOAD_REJECTED`.
4. **Lock the product row, then check the gallery rules:**
   - the product must exist (else `404`) and not be deleted (else `409 INVALID_STATE_TRANSITION`);
   - at most 20 live images (else `422 UPLOAD_REJECTED`).
5. **Store** the re-encoded file under a fresh key.
6. **Insert the row and its audit row**, then commit.

A storage failure leaves no row. A failed commit leaves an orphan file,
which `reap_orphan_files` removes.

## Gallery rules

Every image command row-locks the product (`SELECT … FOR UPDATE`), so cover,
order and the cap are decided one transaction at a time.
`tests/concurrency/test_product_image_races.py` fails without the lock.

- **Uploads:** the first live image becomes the cover. Later uploads append,
  with `sort_order` one past the current maximum.
- **`PUT …/{image_id}/cover`:** clears the old cover first, then sets the new
  one, so the partial unique index is never violated mid-change. Setting the
  current cover again is a no-op `200`.
- **`PUT …/order`:** `image_ids` must list every live image exactly once.
  A missing, extra, duplicate, deleted or foreign id → `422 VALIDATION_ERROR`.
  Positions become 0..n-1.
- **`DELETE …/{image_id}`:** soft delete.
  - Deleting the cover while other live images remain → `409 INVALID_STATE_TRANSITION`; set another cover first.
  - The last image may be deleted.
  - The file is kept, because order lines snapshot the product image (BR-033) and nothing is hard-deleted (BR-018).
- **`PATCH …/{image_id}`:** `{"alt_text": …}`, required. A null or blank
  value clears it; control characters are refused.
- An id that isn't a live image of *this* product is `404`.
- Image changes don't bump the product's `version` (ADR-020 covers product fields only).

`GET /api/v1/admin/products/{id}` and the list now include `images`: the live
ones, in display order.

## Orphan files

`reap_orphan_files` runs daily at 03:41 UTC in the worker. It lists every file
under `products/` and deletes those that are both:

- older than **24 hours** (a constant comfortably above any upload's duration), and
- referenced by no `product_images` row, deleted rows included.

Leftover temporary files from an interrupted write are reaped the same way.

A malware hit or a scanner outage is logged (`product_image_upload_refused`, with the product id and reason, no file content), so a ClamAV outage is visible in the logs and not only through refused uploads.
Files outside `products/` are never touched.

## Audit

All in the same transaction as the change:

| Action | Entity | Before / after |
| --- | --- | --- |
| `product_image.uploaded` | ProductImage | — / row snapshot |
| `product_image.updated` | ProductImage | row snapshots; a no-op is audited with equal before and after |
| `product_image.cover_set` | Product | `cover_image_id` |
| `product_image.reordered` | Product | `image_ids` in order |
| `product_image.deleted` | ProductImage | row snapshots |

## Configuration

`MEDIA_PUBLIC_DIR`, `MEDIA_PUBLIC_URL`, `SCANNER` (`clamav`; `fake` only in
tests and development), `CLAMAV_HOST`, `CLAMAV_PORT`. The docker-compose worker
mounts `./storage/media_public`, so the reaper sees the same files the API writes.
