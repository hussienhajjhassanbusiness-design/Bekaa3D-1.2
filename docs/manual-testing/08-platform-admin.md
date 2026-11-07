# 08 — Platform and admin

Settings, the audit log, business analytics and the customer data export (the Reporting
context), health checks, and the admin boundary every `/api/v1/admin/*` route shares.
Requirements: FR-03 (export), FR-18; BR-124, BR-132, BR-133; SEC-04, SEC-10; ADR-017, ADR-045,
ADR-046.

Code: `src/app/platform/api/settings.py`, `platform/api/audit_logs.py`, `platform/api/schemas.py`,
`platform/domain/settings_registry.py`, `platform/application/commands/update_setting.py`,
`platform/infrastructure/` (`audit_writer.py`, `repositories.py`); Reporting in
`src/app/reporting/api/` (`admin_analytics.py`, `data_export.py`), `reporting/application/`
(`reports.py`, `data_export.py`), `reporting/domain/metrics.py`; health in
`src/app/api/health.py`; the boundary in `src/app/api/v1/admin.py` and
`identity/api/dependencies.py` (`require_admin`, `AdminBoundaryRoute`).

Who-can-call labels: see [01-identity.md](01-identity.md).

---

## The admin boundary

Every route under `/api/v1/admin` runs `require_admin` **before** the body is read, and a hidden
catch-all covers every path that matches no route:

| Caller | Any admin path, real or not, any method |
| --- | --- |
| Anonymous | `401 AUTH_REQUIRED` |
| Signed-in customer | `404 NOT_FOUND`, byte-identical to an unknown path |
| Admin without MFA | `401 MFA_REQUIRED` |
| MFA-complete admin | the route, or `404` / `405` (with `Allow`) for a wrong path or method |

The admin router also limits each administrator to 300 requests per minute
(`ratelimit:admin:<user_id>`).

| ID | Test | Expected |
| --- | --- | --- |
| ADM-01 | Anonymous: `GET /api/v1/admin/settings` and `GET /api/v1/admin/does-not-exist` | both `401 AUTH_REQUIRED` |
| ADM-02 | Customer: the same two | both `404 NOT_FOUND` with the same `title` and `detail` |
| ADM-03 | Customer: `POST /api/v1/admin/categories` with an invalid JSON body | `404 NOT_FOUND` (not `400`: the body is never read) |
| ADM-04 | Admin (MFA): `GET /api/v1/admin/does-not-exist` | `404 NOT_FOUND` |
| ADM-05 | Admin: `DELETE /api/v1/admin/settings` | `405` with an `Allow: GET, HEAD` header |
| ADM-06 | Admin: `GET /api/v1/admin/settings/` (trailing slash) | not a redirect: the same answer an unknown path gets |

---

## Settings

Business parameters are admin-editable typed settings (BR-133); see
[`docs/settings-registry.md`](../settings-registry.md). Types: `boolean`, `integer`, `string`,
`money` (`{"amount_cents", "currency"}`), `duration` (seconds), `json`.

| Key | Type | Default | Public |
| --- | --- | --- | --- |
| `accepting_orders` | boolean | false (seed sets true) | yes |
| `cash_payment_enabled` | boolean | true | yes |
| `cash_max_order_total` | money | 10 000 USD cents | yes |
| `cash_max_open_orders` | integer | 1 | no |
| `manual_max_open_orders` | integer | 3 | no |
| `checkout_hold_period` | duration | 1 800 (30 min) | no |
| `manual_payment_hold_period` | duration | 604 800 (7 days) | no |
| `offer_response_window` | duration | 172 800 (48 h; 1 h to 7 days) | no |
| `offer_checkout_window` | duration | 86 400 (24 h; 1 h to 7 days) | no |
| `offer_rejection_cooldown` | duration | 604 800 (7 days; 0 to 30 days) | no |
| `minimum_offer_percentage` | integer | 70 (0-100) | no |
| `pickup_address`, `pickup_hours`, `whatsapp_number` | string | null | yes |
| `unverified_account_purge_period`, `security_token_retention_period`, `session_retention_period`, `custom_request_attachment_retention` | duration | 30 d, 7 d, 30 d, 90 d | no |

### `GET /api/v1/settings/public`

Anonymous; 600 per hour per IP. A flat object of the six public keys; every key is present, an
unset value is `null`:

```json
{
  "accepting_orders": true,
  "cash_payment_enabled": true,
  "cash_max_order_total": {"amount_cents": 10000, "currency": "USD"},
  "pickup_address": null,
  "pickup_hours": null,
  "whatsapp_number": null
}
```

### `GET /api/v1/admin/settings`

Admin. Ordered by key; `cursor`, `limit` (1-100, 20), `prefix` (≤ 64), `type`. Items:
`{key, type, value, description, unit, minimum, maximum, nullable, is_public, updated_at, updated_by}`.

### `GET /api/v1/admin/settings/{key}`

Admin. `200 SettingRead`; `404` for an unknown key.

### `PATCH /api/v1/admin/settings/{key}`

Admin; CSRF. Body `{"value": …}`. Validated against the setting's type and range; audited in the
same transaction. `200 SettingRead`.

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown key |
| 422 | `SETTING_INVALID` | wrong type, out of range, `null` on a non-nullable key; `detail` lists the reasons |
| 422 | `VALIDATION_ERROR` | a body without `value`, or with another field |

| ID | Test | Expected |
| --- | --- | --- |
| ADM-07 | Anonymous `GET /settings/public` | `200`, six keys |
| ADM-08 | Admin `PATCH /admin/settings/pickup_address` `{"value": "Bekaa3D workshop, Zahle main road"}` | `200`; the public endpoint shows it; pickup checkout now works |
| ADM-09 | `PATCH /admin/settings/minimum_offer_percentage` `{"value": 150}` | `422 SETTING_INVALID` |
| ADM-10 | `PATCH /admin/settings/accepting_orders` `{"value": "yes"}` | `422 SETTING_INVALID` |
| ADM-11 | `PATCH /admin/settings/cash_max_order_total` `{"value": {"amount_cents": 20000, "currency": "USD"}}` | `200`; the public endpoint shows 20000 |
| ADM-12 | `PATCH /admin/settings/no_such_key` | `404 NOT_FOUND` |
| ADM-13 | `GET /admin/settings?prefix=offer_` | only `offer_checkout_window`, `offer_rejection_cooldown`, `offer_response_window` |
| ADM-14 | After ADM-08, `GET /admin/audit-logs?action=setting.updated` | an audit row with before and after values |

---

## Audit log

Read-only. Every admin action, auth event, payment, STL delivery and status change writes a row
(BR-132). Rows are partitioned by month and kept permanently.

### `GET /api/v1/admin/audit-logs`

Admin. Newest first. Query: `cursor`, `limit` (1-100, 20), `actor_user_id`, `action` (≤ 200),
`entity_type` (≤ 200), `entity_id`, `request_id` (≤ 128), `created_after`, `created_before`
(UTC offset required; after < before). Items:
`{id, actor_user_id, action, entity_type, entity_id, before_data, after_data, request_id, created_at}`.

Errors: `422` (bad cursor, a timestamp without offset, an empty range).

### `GET /api/v1/admin/audit-logs/{audit_id}`

Admin. One entry; `404` for an unknown id.

| ID | Test | Expected |
| --- | --- | --- |
| ADM-15 | `GET /admin/audit-logs?action=user.login_failed` | the failed logins from ID-14 |
| ADM-16 | Take the `X-Request-ID` of any admin write, then `GET /admin/audit-logs?request_id=<it>` | exactly that write's row(s) |
| ADM-17 | `GET /admin/audit-logs?created_after=2026-11-01` | `422 VALIDATION_ERROR` naming `created_after` |
| ADM-18 | `created_after` later than `created_before` (both full timestamps) | `422`, "must be later than created_after" |

---

## Business analytics (Reporting)

Admin only, plus a separate limit of **30 per minute per admin** (`admin_analytics`). Ranges are
**dates** in Beirut time (`Asia/Beirut`): `from` and `to` are inclusive `YYYY-MM-DD`; `to`
defaults to today, `from` to 29 days before `to`. A range over 366 days, `to` before `from`, or a
year outside 2020-2100 is **`400 INVALID_DATE_RANGE`**. Revenue is per paid line, net of refunds
and chargebacks; money is in USD cents. ADR-045.

| Method and path | Query | Answer |
| --- | --- | --- |
| `GET /api/v1/admin/analytics/overview` | `from`, `to` | `{from, to, timezone, currency, net {physical_cents, stl_cents, total_cents}, paid_orders, buyers, new_customers, pending_offers {awaiting_admin, awaiting_customer, accepted, total}, stl_lines_awaiting_delivery}` |
| `GET /api/v1/admin/analytics/revenue` | `from`, `to`, `group_by` (`day`, `week`, `month`) | `{…, totals {gross, refunded, net, paid_lines, paid_orders}, buckets [{start, net}], unattributed_chargeback_excess_cents}` |
| `GET /api/v1/admin/analytics/customers` | `from`, `to` | `{…, registered_customers, new_customers, buyers, repeat_buyers, net_per_buyer_cents}` |
| `GET /api/v1/admin/analytics/stl-sales` | `from`, `to`, `limit` (1-100) | `{…, items [{product_id, name, slug, units, lines, net_cents, awaiting_delivery}], stl_lines_awaiting_delivery}` |
| `GET /api/v1/admin/analytics/top-rated-products` | `limit`, `min_reviews` (1-1000, default 3) | `{items [{product_id, name, slug, type, average_rating, review_count, is_visible}]}` |
| `GET /api/v1/admin/analytics/recent-purchases` | `cursor`, `limit` | `{items [{order_id, order_number, user_id, paid_at, payment_method, gross, refunded_cents, net_cents, paid_lines}], next_cursor}` |

Errors: `400 INVALID_DATE_RANGE`, `422 VALIDATION_ERROR` (a date that cannot be parsed,
`limit` out of range), `429 RATE_LIMITED`.

Note the difference: these take **dates**; the Bring Your Idea funnel
(`/admin/analytics/custom-requests/funnel`, [07-engagement.md](07-engagement.md)) takes **full
timestamps** with a UTC offset.

| ID | Test | Expected |
| --- | --- | --- |
| ADM-19 | `GET /admin/analytics/overview` (no query) | `200`; `timezone: Asia/Beirut`; the range is the last 30 days; `net.total_cents` includes PAY-01 and FUL-20 |
| ADM-20 | `GET /admin/analytics/revenue?from=2026-11-01&to=2026-11-30&group_by=week` | `200`; weekly buckets |
| ADM-21 | `GET /admin/analytics/revenue?from=2026-11-30&to=2026-11-01` | `400 INVALID_DATE_RANGE` |
| ADM-22 | `GET /admin/analytics/revenue?from=2024-01-01&to=2026-01-01` (over 366 days) | `400 INVALID_DATE_RANGE` |
| ADM-23 | `GET /admin/analytics/stl-sales` after paying an STL | the STL listed with `units` and `net_cents` |
| ADM-24 | `GET /admin/analytics/top-rated-products?min_reviews=1` | products with at least one visible review |
| ADM-25 | `GET /admin/analytics/recent-purchases` | the latest paid orders, newest first |
| ADM-26 | Customer: `GET /admin/analytics/overview` | `404 NOT_FOUND` |

---

## Customer data export (Reporting)

### `GET /api/v1/me/export`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Verified | **yes, although it is a GET** | no | 3 per day per user |

Streams all of the caller's own data as one JSON document (BR-124, ADR-046):
`{format_version, exported_at, profile, addresses, orders (with lines, payments, refunds, history), reviews, offers (with rounds), contact_messages}`.
Soft-deleted addresses and reviews carry `deleted: true`. Never other users' data, admin notes or
provider references.

| Status | Code | When |
| --- | --- | --- |
| 401 | `AUTH_REQUIRED` | no session |
| 403 | `CSRF_INVALID` / `EMAIL_VERIFICATION_REQUIRED` | no CSRF header; unverified |
| 429 | `RATE_LIMITED` | a 4th export within 24 hours |

| ID | Test | Expected |
| --- | --- | --- |
| ADM-27 | Seed customer with CSRF set in Authorize: `GET /me/export` | `200`; JSON with the customer's addresses, orders, reviews and offers |
| ADM-28 | Without the CSRF header | `403 CSRF_INVALID` |
| ADM-29 | Export 4 times | the 4th `429 RATE_LIMITED` (clear the counters afterwards) |

---

## Health

Outside `/api/v1`, never authenticated. Code: `src/app/api/health.py`.

| Method and path | Answer |
| --- | --- |
| `GET /health/live` | `200 {"status": "ok"}` while the process runs; never probes a dependency |
| `GET /health/ready` | `200 {"status": "ok", "version": "0.1.0", "commit": "…"}`, or `503 SERVICE_UNAVAILABLE` when PostgreSQL or Redis is unreachable |

| ID | Test | Expected |
| --- | --- | --- |
| ADM-30 | `GET /health/live` and `/health/ready` | both `200` |
| ADM-31 | `docker compose stop redis`, then `/health/ready` and `/health/live` | ready `503 SERVICE_UNAVAILABLE`; live still `200`. `docker compose start redis` afterwards |
| ADM-32 | Any request with an `X-Request-ID: my-test-1` header | the response echoes `X-Request-ID: my-test-1` |
