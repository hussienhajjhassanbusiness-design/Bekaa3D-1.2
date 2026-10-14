# Backend Response Template

One block per endpoint or closely-related endpoint group. Copy this block for each item in `BACKEND-UNLOCK-HANDOFF.md`.

**If an OpenAPI spec, Pydantic model, or other schema file already answers this, just tell us the file/path/URL — please don't hand-retype a schema that already exists in code.**

---

```
### Domain / item: <e.g. "C6 — Checkout contract">

Confirmed endpoint:
  <METHOD> <literal path, exact, including version prefix>

Request schema:
  <field: type — required/optional — constraints, for every field>
  (or: "see <OpenAPI file/path/URL>")

Response schema:
  <field: type — always-present/optional, for every field>
  (or: "see <OpenAPI file/path/URL>")

Enums/statuses/actions:
  <exhaustive literal values, not examples — e.g. status: "pending" | "paid" | "failed" | "expired">
  <does the response include a machine-readable "available actions" list? yes/no + field name>

Errors:
  <status code> <problem `code` or type> — <when this happens> — <exact body shape>
  (repeat per distinct error case: validation, conflict, not-found, rate-limit, etc.)

Auth/CSRF/MFA:
  <does this endpoint require the X-CSRF-Token header? auth cookie? admin role? fresh MFA?>

Concurrency/idempotency:
  <idempotency key header name + who generates it + TTL, if applicable>
  <optimistic-lock/version field, if applicable>
  <what happens on a conflicting concurrent write>

Example success JSON:
  <a real, complete example response body>

Example error JSON:
  <one real example per error case listed above>

Fixture/test account:
  <what test data/account this needs to exercise, if anything>

Authoritative source/OpenAPI file:
  <file path, URL, or "none yet">

Notes:
  <anything else worth flagging — a caveat, a "this may change," a dependency on another team>
```

---

## Filled example (for reference only — not a real answer)

```
### Domain / item: C9 — Entitlements/library contract

Confirmed endpoint:
  GET /api/v1/me/entitlements

Request schema:
  cursor: string, optional
  limit: integer, optional, default 20, max 100

Response schema:
  items: array of:
    id: string (uuid)
    product_id: string (uuid)
    product_display_name: string
    thumbnail_url: string, optional
    current_version_label: string, optional
    granted_at: string (ISO 8601, UTC)
  next_cursor: string, optional — absent means no more pages

Enums/statuses/actions:
  none — revoked entitlements are simply excluded from this list, no status field exists

Errors:
  401 AUTH_REQUIRED — no valid session — { type, title, status: 401, detail }

Auth/CSRF/MFA:
  requires valid session cookie; no CSRF header needed (GET); no admin role needed

Concurrency/idempotency:
  not applicable (read-only)

Example success JSON:
  { "items": [{ "id": "...", "product_id": "...", "product_display_name": "Dragon STL", "thumbnail_url": "https://cdn.../dragon.webp", "current_version_label": "v3", "granted_at": "2026-01-15T10:00:00Z" }], "next_cursor": null }

Example error JSON:
  { "type": "https://bekaa3d.com/problems/auth-required", "title": "Authentication required", "status": 401, "detail": "No valid session." }

Fixture/test account:
  one customer with at least one granted entitlement

Authoritative source/OpenAPI file:
  openapi/entitlements.yaml

Notes:
  product_id is also needed by the cart slice (FVS-025) to cross-check already-owned STL products — please keep this field name stable across both reads.
```
