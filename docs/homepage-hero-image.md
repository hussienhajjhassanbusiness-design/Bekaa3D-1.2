# Homepage hero image

The large image on the right of the homepage hero is chosen by an administrator. Until
one is uploaded, the storefront shows its default brand visual.

## Storage

- Setting `homepage_hero_image` (registry, type `string`, nullable, default `null`, not
  public as a setting). Its value is a storage key the upload generates:
  `home/hero/<32 hex>.<jpg|png|webp>`. It is never a URL and never typed by a person:
  the registry refuses any other shape, and the generic
  `PATCH /api/v1/admin/settings/homepage_hero_image` accepts only `null`. `null` clears
  it and restores the default visual.
- The file is stored in public media (`MEDIA_PUBLIC_DIR`) and served at
  `MEDIA_PUBLIC_URL/home/hero/...`, like product images. In local development the API
  does not serve `/media`: the Compose `media` service serves `storage/media_public`
  read-only on `http://localhost:8001`, the frontend's dev `/media` proxy target. Without
  it, the image URL fails and the homepage falls back to its default visual.
- Seeded by migration `c8e2f4a6b1d3` as JSON `null`.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| `PUT` | `/api/v1/admin/home/hero-image` | Administrator + MFA, CSRF. Multipart `file`. 200 `{"url": "/media/home/hero/....webp"}` |
| `GET` | `/api/v1/home/hero-image` | Public, rate limited (600/hour per IP). `{"url": string \| null}` |

The public read is its own endpoint, not a field of `GET /api/v1/settings/public`, because
that response's fixed six-field schema is its security design. A stored value that fails
validation reads as `null`, so the homepage falls back to the default visual instead of
breaking.

## Upload rules

These follow the product-image pipeline (ADR-021):

- The `Content-Length` must be at most 10 MB plus the multipart allowance. A larger body is
  refused before it is read.
- Malware scan of the raw bytes. If the scanner is unavailable the upload fails closed with
  `503 SERVICE_UNAVAILABLE`. A detection answers `422 MALWARE_DETECTED`.
- The format is read from the content (magic bytes), never from the file name or
  Content-Type. JPEG, PNG and WebP only. Anything else, including SVG, GIF and
  executables, answers `422 UPLOAD_REJECTED`. The image is re-encoded with its metadata
  stripped, at most 40 MP.
- The image must be at least 400 px on each side.
- The file is stored first, then the setting is updated and audited (`setting.updated`)
  in the request's transaction. Any refusal leaves the current image in place.

## Replaced images

A replaced file is not deleted at once, because a page loaded a moment earlier may still
request it. It is no longer referenced, so the daily `reap_orphan_files` job (target
`home/hero/`) removes it once it is older than the 24-hour grace period. Only files under
`home/hero/` belong to this feature; no other media is touched.
