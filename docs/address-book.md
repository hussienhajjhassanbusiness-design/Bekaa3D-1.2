# Address book (VS-026)

The customer's saved Lebanese delivery addresses. Decisions and rationale: [ADR-027](adr/ADR-027-address-book-decisions.md). Requirements: SRS §14.4, BR-027, BR-071, BR-078, BR-123, F-025, FR-03.

## Routes

| Method + path | Auth | Success | Errors |
|---|---|---|---|
| `GET /api/v1/me/addresses` | Signed in (unverified allowed) | `200 AddressList` | 401 |
| `POST /api/v1/me/addresses` | Verified + `X-CSRF-Token` | `201 AddressRead` | 401, 403, 422 `VALIDATION_ERROR` / `ADDRESS_LIMIT_REACHED` |
| `GET /api/v1/me/addresses/{address_id}` | Signed in (unverified allowed) | `200 AddressRead` | 401, 404 |
| `PATCH /api/v1/me/addresses/{address_id}` | Verified + CSRF | `200 AddressRead` | 401, 403, 404, 422 |
| `DELETE /api/v1/me/addresses/{address_id}` | Verified + CSRF | `204` | 401, 403, 404 |
| `PUT /api/v1/me/addresses/{address_id}/default` | Verified + CSRF | `200 AddressRead` | 401, 403, 404 |

- `403` is `CSRF_INVALID` or `EMAIL_VERIFICATION_REQUIRED`.
- `404 NOT_FOUND` is the same body for another user's address, a deleted one and an unknown id.

## Fields

| Field | Create | Rule |
|---|---|---|
| `label` | required | 1-50 characters, single line |
| `recipient_name` | required | 1-100, single line |
| `phone` | required | A Lebanese number in any common spelling (`+961 3 123 456`, `03 123 456`, `71 123 456`, `00961…`). Stored and returned as E.164, e.g. `+9613123456`. |
| `governorate` | required | `akkar`, `baalbek_hermel`, `beirut`, `beqaa`, `keserwan_jbeil`, `mount_lebanon`, `nabatieh`, `north`, `south` |
| `city` | required | 1-100, single line |
| `area` | optional | up to 100, single line; blank or `null` stores `null` |
| `street` | optional | up to 200, single line; blank or `null` stores `null` |
| `landmark_notes` | **required** | 1-500, line breaks allowed |
| `is_default` | optional | see below |

- Values are trimmed. Unknown fields are refused (`422`). There is no country or postal code.
- `AddressRead` adds `id`, `is_default`, `created_at` and `updated_at`.
- `PATCH` takes any subset of the fields. An empty body is `422`. `null` clears `area` or `street`; on a required field it is `422`.

## Default address

- At most one live default per user, enforced by a partial unique index.
- A user's **first** live address becomes the default, even with `is_default: false`. Later ones never become default on their own.
- `PUT …/default`, or `is_default: true` on create or update, makes an address the default and clears the previous one in the same transaction. `PATCH is_default: false` on the default clears it.
- Deleting the default leaves no default.
- The list returns the default first, then newest first.

## Limits and deletion

- At most **20** live addresses per user (`422 ADDRESS_LIMIT_REACHED`). Deleted addresses do not count.
- `DELETE` is a soft delete: the row keeps `deleted_at` and stops being default. Past orders keep their own address snapshot (VS-028), so deleting or editing an address never changes an order.

## Concurrency

Every write takes the per-user lock (`users` row, `FOR NO KEY UPDATE`) before it reads anything. Parallel default switches, parallel first creates and parallel creates at the cap each end with exactly one default and never more than 20 addresses (`tests/concurrency/test_address_default_race.py`).
