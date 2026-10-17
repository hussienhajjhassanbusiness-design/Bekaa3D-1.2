# Bring Your Idea submissions (VS-034)

A guest describes a custom print and may attach reference images. The request is a **lead, not a transaction** (BR-112): no cart, order or payment is ever created. Decisions and rationale: [ADR-030](adr/ADR-030-bring-your-idea-submission.md). Requirements: SRS §13, BR-110-BR-115, SEC-11-SEC-16, FR-15. The admin pipeline is VS-035.

## Route

| Method + path | Auth | Success | Errors |
|---|---|---|---|
| `POST /api/v1/custom-requests` | Public; no auth cookies or CSRF; Turnstile captcha | `201 CustomRequestReceipt` (`id`, `created_at`) | 400 `CAPTCHA_INVALID`, 422 `VALIDATION_ERROR` / `UPLOAD_REJECTED` / `MALWARE_DETECTED`, 429 `RATE_LIMITED`, 503 `SERVICE_UNAVAILABLE` |

The body is `multipart/form-data`. The receipt carries no attachment URL or key.

| Part | Rule |
|---|---|
| `name` | required, 1-100, single line |
| `email` | required, an email address |
| `phone` | required, up to 32: digits, spaces, `+ ( ) . -`, at least 6 digits |
| `project_title` | required, 1-200, single line |
| `description` | required, 1-5000, line breaks allowed |
| `preferred_material`, `preferred_colour` | optional, up to 100, free text |
| `dimensions` | optional, up to 200, free text |
| `captcha_token` | required, the Turnstile token |
| `attachments` | 0 to 5 file parts named exactly `attachments` (no brackets; parts under any other name are ignored), each a JPEG, PNG or WebP of at most 10 MB and 40 MP. **Omit the part entirely when there are no images**; a blank file part is `422`. |

An empty text part counts as absent: an empty optional field stores `null`, and an empty required field (including `captcha_token`) is `422 VALIDATION_ERROR`.

## Order of checks

1. **Before the body is parsed:** 20 attempts per IP per hour (`429`), and a declared `Content-Length` of at most 5 × 10 MB + 64 KiB (`422 UPLOAD_REJECTED`; a missing `Content-Length` is refused too).
2. **Fields, file count and file sizes** (`422`). Nothing has been verified or counted yet.
3. **Captcha** (`400 CAPTCHA_INVALID`; an outage is `503` with `Retry-After: 30`).
4. **5 per hour per IP and 5 per hour per email** (`429`). The email is hashed in Redis.
5. **Each file, in order** (ADR-021): scan the raw bytes (`422 MALWARE_DETECTED`; scanner down is `503`), sniff the type by content, decode, re-encode (`422 UPLOAD_REJECTED`). Filenames and `Content-Type` are ignored.
6. **Store, insert, notify, commit.**

A refusal at any step stores nothing. `UPLOAD_REJECTED` and `MALWARE_DETECTED` name the failing file in `errors[].loc` (`["body", "attachments", <index>]`).

## Storage

- Files live under `UPLOADS_PRIVATE_DIR` (`/data/uploads_private`), never under the web root, as `custom-requests/<uuid4>.<jpg|png|webp>`. Only the re-encoded output is written; EXIF, GPS, ICC and trailing bytes never survive.
- Every file is screened before any is written. If anything fails before commit, the files already written are deleted. A failed commit leaves orphans that `reap_orphan_files` removes after 24 hours.
- The worker mounts the same directory (`docker-compose.yml`).

## Tables (migration `26d5d039d72c`)

`custom_requests` follows database-design.md §12.4 without `user_id`. It also has the pipeline columns VS-035 will write: `quoted_amount_cents` + `currency` (USD only, both or neither, ≥ 0), `outcome`, `admin_notes` (≤ 5000), `contacted_at`, `quoted_at`, `completed_at`, `closed_at`, and the queue index `(status, created_at, id)`. Every text column has a length and non-blank CHECK.

`custom_request_attachments` follows §12.5:

| Constraint | Rule |
|---|---|
| `ck_..._storage_key_format` | only generated keys under `custom-requests/` |
| `uq_..._storage_key` | two rows never share a file |
| `ck_..._mime_type` | `image/jpeg`, `image/png` or `image/webp` |
| `ck_..._size_positive`, `ck_..._checksum_sha256` | size > 0; SHA-256 hex of the stored bytes |
| `ck_..._filename_length` | the display name, 1-255 characters |
| `ck_..._expires_after_created` | `expires_at > created_at` |
| `scan_status` | enum `upload_scan_status`, whose only value is `clean` |

## Retention

- `expires_at` = submission time + the `custom_request_attachment_retention` setting (90 days by default, 1-365 days), stamped at submission. Changing the setting affects new attachments only.
- `purge_expired_attachments` runs daily at 03:35 UTC. Per batch of 500 (at most 50 batches a run) it locks rows with `expires_at <= now` using `SKIP LOCKED`, deletes the files, then the rows. The request row is kept. A second run, or a row whose file is already gone, is harmless.

## Notifications

On success every active, live administrator gets one in-app notification of type `custom_request` (a seventh category, ADR-030), in the same transaction:

```json
{"event": "custom_request.submitted", "custom_request_id": "<uuid>",
 "project_title": "<title>", "title": "New Bring Your Idea request: <title>"}
```

It never contains the visitor's name, email or phone. A refused submission notifies nobody. Each insert runs in its own savepoint: a failed notification is logged (`custom_request_notification_failed`) and the request is still stored (FR-15).

## Logs

Only `custom_request_received` with the request id and attachment count, `custom_request_upload_refused` with a reason and file index, and `custom_request_notification_failed` with the request id and a count. Names, emails, phones, descriptions and file contents are never logged.
