# Bekaa3D — Database Design

**Document:** `database-design.md`  
**Status:** Step 12 — Database Design COMPLETE / Schema Frozen for V1; revised 2026-10-06 for ADR-019 (manual STL delivery)  
**Database:** PostgreSQL 16  
**ORM / migrations:** SQLAlchemy 2.0 Async + Alembic  
**Source of truth:** `Bekaa3D_SRS_Complete.md`  
**Purpose:** Convert the approved domain model and business rules into an implementation-ready relational database design before SQLAlchemy models or migrations are written.


## Schema Freeze Summary

The V1 relational design is now complete. Where the approved SRS was silent on a low-level implementation detail, this document records an explicit **V1 design assumption** rather than presenting it as an SRS requirement. Material business changes still require the SRS/ERD to be updated first.

Final Step-12 decisions include:

- no shipping amounts, zones or threshold: the courier prices and collects delivery (ADR-024, superseding the earlier explicit zone-selection decision);
- cash on delivery as an order `payment_method`, recorded as a `cash` payment at handover (ADR-024);
- conservative 1-year capacity envelopes for schema/index review;
- frozen implementation enum values;
- soft-deleted wishlist rows;
- refresh-token rotation/reuse detection using session token versions;
- explicit retention exceptions for data the SRS requires to be physically purged.

---

---

## 1. Design Principles

1. The database is the final integrity boundary. Application validation gives useful errors; database constraints prevent invalid states under concurrency.
2. Business-history records are preserved. Orders, order lines, payments, refunds, offer history, STL delivery records, and audit history are not casually deleted.
3. Monetary snapshots and order-line snapshots are immutable after placement.
4. Order status is a projection of payment and line states; application code must not treat it as an independently editable business field.
5. External identifiers, user input, prices, payment callbacks, and client-computed totals are never trusted without server-side validation.
6. PostgreSQL constraints and partial unique indexes enforce invariants that application-level “check then insert” logic could race on.
7. The schema is designed for the V1 scale target: at least 10,000 catalogue products and 200 concurrent users without an index redesign.
8. Redis, workers, caching, and other infrastructure do not replace relational integrity.

---

# 2. Global Database Conventions

| Concern | Standard |
|---|---|
| Database | PostgreSQL 16 |
| Table naming | plural `snake_case` |
| Column naming | `snake_case` |
| Primary keys | UUID, time-ordered where available |
| Foreign keys | `<entity>_id` |
| Timestamps | `TIMESTAMPTZ`, UTC |
| Money | `BIGINT` integer cents + `CHAR(3)` currency |
| Currency in V1 | USD |
| JSON | `JSONB` only |
| Enums | Native PostgreSQL enum types |
| Soft delete | nullable `deleted_at` on soft-deletable entities |
| Search | PostgreSQL FTS + trigram |
| Migrations | Alembic, forward-only operational posture, expand-contract for production changes |
| Email | `CITEXT` |
| Nullability | `NOT NULL` by default; nullable only for a named business reason |
| External list queries | bounded/paginated |
| Historical snapshots | copied into order/order-item rows; never read from mutable catalogue data |

### 2.1 Required PostgreSQL Extensions

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS btree_gin;
```

### 2.2 Standard Timestamp Columns

Normal mutable entities generally use:

```text
created_at TIMESTAMPTZ NOT NULL
updated_at TIMESTAMPTZ NOT NULL
```

Append-only entities generally use only:

```text
created_at TIMESTAMPTZ NOT NULL
```

Soft-deletable entities use:

```text
deleted_at TIMESTAMPTZ NULL
```

### 2.3 Money Rules

Every monetary amount uses integer cents:

```text
price_cents BIGINT
total_cents BIGINT
amount_cents BIGINT
```

Every monetary row also carries:

```text
currency CHAR(3)
```

V1 business rule:

```text
currency = 'USD'
```

Never use `FLOAT`, `REAL`, or binary floating-point for money.

### 2.4 Known Deletion/Retention Specification Tension

The business-rules register contains a blanket statement that entities use soft delete, while later requirements explicitly require:

- purging never-verified accounts after a configured period;
- purging expired custom-request attachments from disk and database;
- archiving old audit partitions.

**Design resolution used in this document:** core business/catalogue records use soft delete or anonymisation; ephemeral/security tokens and explicit retention-managed records may be physically purged when their specific retention rule requires it.

This resolution must be kept visible in the project documentation. If the product owner intends “never hard delete” literally even for ephemeral/retention data, this policy must be revised before migrations are created.

---

# 3. Enum Catalogue

The exact PostgreSQL enum names may change during implementation, but these values represent the approved state models.

## 3.1 `user_role`

```text
customer
admin
```

Future roles may be added without redesigning the user table.

## 3.2 `product_type`

```text
physical
stl
```

## 3.3 `purchase_mode`

```text
online_only
whatsapp_only
both
```

## 3.4 `fulfillment_method`

```text
delivery
pickup
```

`NULL` means no physical fulfillment, as in a digital-only order.

## 3.4a `payment_method`

```text
online
cash
```

Chosen at checkout and immutable (ADR-024). `cash` requires every line to be physical. Distinct from `purchase_mode` and `fulfillment_method`.

## 3.4b `cancel_reason`

```text
refused
no_show
other
```

Recorded on an administrator cancel from `ready_to_ship` or `returned` (`refused` or `other`) or `ready_for_pickup` (`refused`, `no_show` or `other`). Only `refused` and `no_show` can create a cash payment block (ADR-024).

## 3.5 `order_source`

```text
cart
offer
```

## 3.6 `order_status`

Derived projection only:

```text
pending_payment
cancelled
refunded
partially_refunded
completed
in_progress
```

## 3.7 `order_item_status`

Combined storage enum for line state. Legal transitions depend on product type, fulfillment method and payment method. STL lines use `pending → awaiting_delivery → delivered`, and `refunded` (ADR-019). Physical `in_production` is internal and shown to customers as `pending` (ADR-024).

```text
pending
awaiting_delivery
in_production
ready_to_ship
shipped
delivered
returned
ready_for_pickup
picked_up
cancelled
refunded
```

## 3.8 `payment_status`

```text
pending
processing
paid
partially_refunded
refunded
failed
expired
```

## 3.9 `offer_status`

```text
awaiting_admin
awaiting_customer
accepted
rejected
expired
withdrawn
paid
checkout_expired
auto_closed
```

## 3.10 `offer_turn`

```text
admin
customer
```

## 3.11 `custom_request_status`

```text
new
contacted
quoted
in_progress
completed
closed
lost
```

## 3.12 `contact_message_status`

```text
new
read
replied
archived
```

## 3.13 Final Implementation Enums

The SRS requires these concepts but does not prescribe every exact implementation value. The following values are **V1 schema-freeze decisions**, not new business requirements.

### `malware_scan_status`

```text
pending
clean
infected
failed
```

### `refund_status`

```text
pending
settled
failed
```

`failed` refunds stay owed until reissued (ADR-024).

### `refund_kind`

```text
admin
cancellation
late_capture
chargeback
```

Every V1 refund is manual, so there is no `refund_method` (ADR-024).

### `offer_actor`

```text
customer
admin
system
```

### `offer_action`

```text
submitted
countered
accepted
rejected
withdrawn
expired
paid
checkout_expired
auto_closed
```

### `notification_type`

```text
account
order
payment
refund
offer
download
custom_request
```

`custom_request` was added by VS-034 for the administrator's "new Bring Your Idea request" notification (ADR-030). The specific event is carried in the JSON payload; the enum remains a stable high-level category. Since ADR-019, `download` is the category for the "STL file sent" event (`payload.event = "stl.delivered"`); the value is kept because renaming a PostgreSQL enum value is a migration for no behavioural gain.

### `setting_type`

```text
boolean
integer
string
money
duration
json
```

### `outbox_status`

```text
pending
sending
sent
failed
```

### `custom_request_outcome`

```text
won
lost
```

### `payment_provider`

```text
mock
cash
```

`cash` has no adapter: only the administrator's cash handover creates a `cash` payment (ADR-024). It is a value here, rather than a separate column, so one live-payment index and one refund path cover both kinds; the glossary's Payment Method (`online`/`cash`) is still a separate concept on the order. The online provider is undecided (SRS §30.4); VS-032 adds its value(s) with an additive enum migration before its adapter is enabled. Each attempt's provider is stored on its row: chosen by the customer at checkout or retry when more than one is configured. `mock` is never configured in production.

---

# 4. Entity Inventory

## Identity / Security

1. `users`
2. `addresses`
3. `sessions`
4. `verification_tokens`
5. `password_reset_tokens`
6. `mfa_credentials`
7. `mfa_recovery_codes`

> The two MFA tables are security-support persistence required by SEC-04. They do not change the SRS business-domain model.

## Catalogue

8. `products`
9. `product_images`
10. `categories`
11. `materials`
12. `colours`

## Digital Assets

13–17. Removed by ADR-019 (`asset_versions`, `stl_assets`, `entitlements`, `downloads`, `download_stats_monthly`). Numbers are not reused.

## Ordering

18. `carts`
19. `cart_items`
20. `orders`
21. `order_items`
22. `order_status_history`
22a. `cash_payment_blocks` (ADR-024)

## Payments

23. `payments`
24. `webhook_events`
25. `refunds`
26. `refund_items`

## Fulfillment

27. ~~`shipping_zones`~~ — removed by ADR-024; Fulfillment owns no tables of its own.

## Negotiation

28. `offers`
29. `offer_rounds`

## Engagement

30. `reviews`
31. `wishlist_items`
32. `notifications`
33. `custom_requests`
34. `custom_request_attachments`
35. `contact_messages`

## Platform

36. `settings`
37. `audit_logs`
38. `email_outbox`
39. `idempotency_records`

---

# 5. Identity Tables

## 5.1 `users`

**Purpose:** Stores customer and administrator accounts.

| Column | Type | Null | Key / Constraint | Notes |
|---|---|---:|---|---|
| `id` | UUID | No | PK | Time-ordered UUID preferred |
| `email` | CITEXT | No | partial unique | Login identifier |
| `password_hash` | TEXT | No |  | Argon2id hash |
| `role` | `user_role` | No |  | Default `customer` |
| `email_verified_at` | TIMESTAMPTZ | Yes |  | `NULL` = unverified |
| `is_active` | BOOLEAN | No |  | Default `TRUE` |
| `anonymized_at` | TIMESTAMPTZ | Yes |  | Account deletion/anonymisation |
| `deleted_at` | TIMESTAMPTZ | Yes |  | Soft-delete marker where applicable |
| `created_at` | TIMESTAMPTZ | No |  | UTC |
| `updated_at` | TIMESTAMPTZ | No |  | UTC |

### Constraints

```text
UNIQUE lower(email) WHERE deleted_at IS NULL
```

Because `CITEXT` is used, the implementation may use a direct unique partial index on `email` instead of `lower(email)`.

### Deletion

- Verified customers: anonymise rather than purge.
- Login is disabled after anonymisation.
- Financial and STL delivery records remain.
- Deletion is blocked while orders are open or refunds are unsettled.
- Never-verified accounts may be physically purged after the configured retention period.

### Important Indexes

- unique live email;
- `created_at` if admin customer reporting requires it;
- `email_verified_at`/`created_at` partial index may be added for the unverified-account purge job.

---

## 5.2 `addresses`

**Purpose:** Customer saved delivery address book.

| Column | Type | Null | Key / Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `user_id` | UUID | No | FK → `users.id` |
| `label` | TEXT | No | 1-50 characters |
| `recipient_name` | TEXT | No | 1-100 characters |
| `phone` | TEXT | No | Lebanese number in E.164 (`^\+961[0-9]{7,8}$`); the courier's contact |
| `governorate` | TEXT | No | One of the nine governorate slugs (CHECK) |
| `city` | TEXT | No |  |
| `area` | TEXT | Yes |  |
| `street` | TEXT | Yes |  |
| `landmark_notes` | TEXT | No | Required: SRS 14.4 (ADR-027); 1-500 characters |
| `is_default` | BOOLEAN | No | Default `FALSE` |
| `deleted_at` | TIMESTAMPTZ | Yes |  |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

### Constraints

At most one active default address per user:

```text
UNIQUE(user_id)
WHERE is_default = TRUE AND deleted_at IS NULL
```

A deleted address is never default: `CHECK (NOT (is_default AND deleted_at IS NOT NULL))`. Text columns carry length and non-blank checks. Every write first locks the owner's `users` row `FOR NO KEY UPDATE` (ADR-027).

### FK Delete

`users → addresses`: `ON DELETE CASCADE`, which fires only in the physical purge of a never-verified account; no foreign key to `users` may block that purge. Normal verified-account deletion is anonymisation, not hard deletion.

### Important Note

Orders do **not** depend on the mutable address row for historical truth. Address data is copied into the order as an immutable snapshot.

---

## 5.3 `sessions`

**Purpose:** Stores hashed rotating refresh-token/session state.

| Column | Type | Null | Key / Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `user_id` | UUID | No | FK → `users.id` |
| `refresh_token_hash` | TEXT | No | UNIQUE |
| `token_version` | INTEGER | No | Default `1`; CHECK > 0 |
| `expires_at` | TIMESTAMPTZ | No |  |
| `last_used_at` | TIMESTAMPTZ | Yes |  |
| `rotated_at` | TIMESTAMPTZ | Yes | last successful rotation |
| `revoked_at` | TIMESTAMPTZ | Yes |  |
| `reuse_detected_at` | TIMESTAMPTZ | Yes | stale-token reuse detection |
| `ip_hash` | TEXT | Yes |  |
| `user_agent` | TEXT | Yes |  |
| `created_at` | TIMESTAMPTZ | No |  |

### FK Delete

`ON DELETE CASCADE` for an account that is legitimately physically purged.

### Indexes

```text
(user_id)
(expires_at) WHERE revoked_at IS NULL
```

### Refresh-Token Rotation / Reuse Detection — Final V1 Decision

One `sessions` row represents one browser/device login session.

The refresh token contains a signed reference to the session plus its `token_version`. On successful refresh:

1. lock the session row;
2. verify it is not revoked/expired;
3. verify the presented version and token hash;
4. issue a new refresh token;
5. replace `refresh_token_hash`;
6. increment `token_version`;
7. set `rotated_at`.

If a validly signed token references the session but carries an older version, treat it as **refresh-token reuse**:

```text
reuse_detected_at = now()
revoked_at = now()
```

and require a new login.

This gives rotation/reuse protection without creating a separate refresh-token-history table.

---

## 5.4 `verification_tokens`

| Column | Type | Null | Key / Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `user_id` | UUID | No | FK → `users.id` |
| `token_hash` | TEXT | No | UNIQUE |
| `expires_at` | TIMESTAMPTZ | No |  |
| `used_at` | TIMESTAMPTZ | Yes |  |
| `created_at` | TIMESTAMPTZ | No |  |

### Retention

Ephemeral. Expired/used rows may be purged according to security retention policy.

---

## 5.5 `password_reset_tokens`

| Column | Type | Null | Key / Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `user_id` | UUID | No | FK → `users.id` |
| `token_hash` | TEXT | No | UNIQUE |
| `expires_at` | TIMESTAMPTZ | No |  |
| `used_at` | TIMESTAMPTZ | Yes |  |
| `created_at` | TIMESTAMPTZ | No |  |

### Retention

Ephemeral. Expired/used rows may be purged.

---

## 5.6 `mfa_credentials`

**Purpose:** One optional MFA credential per account; required for administrators before full admin access.

| Column | Type | Null | Key / Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `user_id` | UUID | No | FK → `users.id`; UNIQUE |
| `method` | TEXT / enum | No | V1 = `totp` |
| `secret_ciphertext` | BYTEA | No | application-encrypted TOTP secret |
| `enabled_at` | TIMESTAMPTZ | Yes | NULL until enrollment confirmed |
| `last_used_at` | TIMESTAMPTZ | Yes |  |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

### Rules

- admin access requires an enabled MFA credential;
- the raw TOTP secret is never stored plaintext;
- enrollment creates/updates the credential but `enabled_at` remains NULL until a valid TOTP is confirmed;
- deleting/disabling MFA is not a normal V1 admin action because SEC-04 treats MFA as required.

### FK Delete

`ON DELETE CASCADE` is acceptable only when a user is legitimately physically purged. Normal verified-user deletion remains anonymisation.

---

## 5.7 `mfa_recovery_codes`

**Purpose:** One-time recovery codes for an enabled MFA credential.

| Column | Type | Null | Key / Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `mfa_credential_id` | UUID | No | FK → `mfa_credentials.id` |
| `code_hash` | TEXT | No | UNIQUE |
| `used_at` | TIMESTAMPTZ | Yes | one-time use |
| `created_at` | TIMESTAMPTZ | No |  |

### Rules

- only hashes are stored;
- plaintext recovery codes are returned once at generation time;
- successful recovery-code use sets `used_at`;
- regeneration invalidates/removes prior unused code set and creates a new set;
- MFA recovery events are audit-logged.

### Index

```text
(mfa_credential_id) WHERE used_at IS NULL
```

### FK Delete

`mfa_credentials → mfa_recovery_codes`: `ON DELETE CASCADE`.

---

# 6. Catalogue Tables

## 6.1 `categories`

**Purpose:** Main product categories. V1 has no category hierarchy/subcategories.

| Column | Type | Null | Key / Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `name` | TEXT | No |  |
| `slug` | TEXT | No | partial unique |
| `is_active` | BOOLEAN | No | Default `TRUE` |
| `deleted_at` | TIMESTAMPTZ | Yes |  |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

### Constraints

```text
UNIQUE(slug) WHERE deleted_at IS NULL
```

### Rules

- A category cannot be deleted/archive-finalised while products are assigned.
- Products must be reassigned first.
- Storefront products must belong to an active category.
- Soft-deleting a category releases its slug (same-transaction `deleted_at`).

### FK Delete

`products.category_id → categories.id` uses `ON DELETE RESTRICT`.

---

## 6.2 `materials`

**Purpose:** Admin-managed controlled material list used for physical product faceting.

| Column | Type | Null |
|---|---|---:|
| `id` | UUID | No |
| `name` | TEXT | No |
| `is_active` | BOOLEAN | No |
| `deleted_at` | TIMESTAMPTZ | Yes |
| `created_at` | TIMESTAMPTZ | No |
| `updated_at` | TIMESTAMPTZ | No |

Products referencing a material prevent destructive removal.

---

## 6.3 `colours`

**Purpose:** Admin-managed controlled colour list used for physical product faceting.

| Column | Type | Null |
|---|---|---:|
| `id` | UUID | No |
| `name` | TEXT | No |
| `is_active` | BOOLEAN | No |
| `deleted_at` | TIMESTAMPTZ | Yes |
| `created_at` | TIMESTAMPTZ | No |
| `updated_at` | TIMESTAMPTZ | No |

---

## 6.4 `products`

**Purpose:** Single catalogue root for both physical products and STL products. Catalogue text (name, description, slug, SEO metadata) lives directly on this table — see ADR-016; there is no separate translation table.

**Important:** There is no `stock_quantity`; physical products are manufactured on demand.

| Column | Type | Null | Key / Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `type` | `product_type` | No | type-integrity checks |
| `category_id` | UUID | No | FK → `categories.id` |
| `name` | TEXT | No |  |
| `description` | TEXT | Yes |  |
| `slug` | TEXT | No | partial unique |
| `seo_title` | TEXT | Yes |  |
| `seo_description` | TEXT | Yes |  |
| `og_image_url` | TEXT | Yes |  |
| `search_vector` | TSVECTOR | No | generated/stored |
| `price_cents` | BIGINT | No | CHECK ≥ 0 |
| `currency` | CHAR(3) | No | CHECK = `USD` in V1 |
| `is_visible` | BOOLEAN | No | Default `FALSE` |
| `is_featured` | BOOLEAN | No | Default `FALSE` |
| `is_available` | BOOLEAN | No | Default `TRUE` |
| `average_rating` | NUMERIC(3,2) | No | Default 0; CHECK 0..5 |
| `review_count` | INTEGER | No | Default 0; CHECK ≥ 0 |
| `wishlist_count` | INTEGER | No | Default 0; CHECK ≥ 0 |
| `purchase_mode` | `purchase_mode` | Yes | physical only |
| `material_id` | UUID | Yes | FK → `materials.id`; physical only |
| `colour_id` | UUID | Yes | FK → `colours.id`; physical only |
| `dimensions` | JSONB | Yes | physical only |
| `production_lead_time_days` | INTEGER | Yes | physical only; CHECK ≥ 0 |
| `batch_size` | INTEGER | Yes | physical only; CHECK > 0 |
| `max_quantity_per_line` | INTEGER | Yes | physical only; CHECK > 0 |
| `weight_grams` | INTEGER | Yes | physical only; optional; CHECK > 0 when present |
| `version` | INTEGER | No | Default 1; CHECK ≥ 1; optimistic concurrency for admin edits (ADR-020, added by VS-013) |
| `deleted_at` | TIMESTAMPTZ | Yes |  |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

### Constraints

```text
UNIQUE(slug) WHERE deleted_at IS NULL
```

```text
UNIQUE(id, type)   -- uq_products_id_type: target of cart_items' composite FK (VS-022, ADR-029)
```

### Type Integrity

For `physical`:

```text
purchase_mode IS NOT NULL
production_lead_time_days IS NOT NULL
batch_size IS NOT NULL AND batch_size > 0
max_quantity_per_line IS NOT NULL AND max_quantity_per_line > 0
```

Material and colour are catalogue attributes but the SRS does not explicitly state they are mandatory for every physical product; keep them nullable unless the approved requirement is tightened.

For `stl`:

```text
purchase_mode IS NULL
material_id IS NULL
colour_id IS NULL
dimensions IS NULL
production_lead_time_days IS NULL
batch_size IS NULL
max_quantity_per_line IS NULL
weight_grams IS NULL
```

### Important Rules

- WhatsApp-only products may be viewed but cannot enter cart/checkout.
- Unavailable products remain visible for SEO but cannot be added to cart.
- Product purchase mode and availability are revalidated at checkout.
- No variants are modeled in V1.
- Catalogue price is mutable; order-line price is an immutable snapshot.
- `average_rating`, `review_count`, and `wishlist_count` are maintained aggregates, not client-supplied values.
- Soft-deleting a product releases its slug (same-transaction `deleted_at`).

### Search

- PostgreSQL `english` text search configuration only.
- Search vector weights product name above description.
- Trigram index on name supports typo tolerance/autocomplete.

### FK Delete

- category/material/colour references: `ON DELETE RESTRICT`.
- order history referencing products: `ON DELETE RESTRICT`.

---

## 6.5 `product_images`

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `product_id` | UUID | No | FK → `products.id` |
| `storage_key` | TEXT | No |  |
| `alt_text` | TEXT | Yes | implementation choice |
| `sort_order` | INTEGER | No | CHECK ≥ 0 |
| `is_cover` | BOOLEAN | No | Default `FALSE` |
| `deleted_at` | TIMESTAMPTZ | Yes | soft-delete marker |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

### Constraint

At most one **active** cover image per product:

```text
UNIQUE(product_id)
WHERE is_cover = TRUE AND deleted_at IS NULL
```

### Deletion

Admin image removal soft-deletes the metadata row. The physical media object may be garbage-collected later only when storage-retention policy confirms it is no longer referenced.

---

# 7. Digital Asset Tables

Removed by ADR-019 (2026-10-06). The platform stores no STL files, so `asset_versions`, `stl_assets`, `entitlements`, `downloads` and `download_stats_monthly` are not created. STL ownership and delivery live on `order_items` (§8.4) and `orders.customer_email_snapshot` (§8.3).

---

# 8. Cart and Ordering Tables

## 8.1 `carts`

**Purpose:** One persistent cart per registered customer.

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `user_id` | UUID | No | FK → `users.id`; UNIQUE |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

### Rules

- one cart per customer;
- may mix physical and STL lines;
- write access requires verified email.

---

## 8.2 `cart_items`

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `cart_id` | UUID | No | FK → `carts.id` |
| `product_id` | UUID | No | FK → `products.id` |
| `product_type` | `product_type` | No | snapshot; composite FK `(product_id, product_type)` → `products (id, type)` (ADR-029) |
| `quantity` | INTEGER | No | CHECK > 0 |
| `price_snapshot_cents` | BIGINT | No | CHECK ≥ 0 |
| `currency` | CHAR(3) | No | CHECK = `USD` |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

### Critical Constraint

```text
UNIQUE(cart_id, product_id)
```

### Rules

- adding the same product merges quantity;
- STL quantity must equal exactly 1;
- physical quantity must stay at/below current product cap;
- already-owned STL (a paid, unrefunded line, §8.4) cannot be added;
- unavailable / deleted / invisible / WhatsApp-only products cannot be purchased online;
- price snapshot is compared with current product price during checkout.

### STL Quantity Check

The database can enforce:

```text
quantity > 0
```

but determining whether the referenced product is STL is cross-table. VS-022 therefore snapshots the type onto the line (`product_type`), proves the snapshot with a composite FK to a new `UNIQUE (products.id, type)` (`ON UPDATE RESTRICT`), and adds `CHECK (product_type <> 'stl' OR quantity = 1)` (SRS §21.2, ADR-029). Lines are hard-deleted (ADR-029). The service also enforces the rule, for a readable error.

---

## 8.3 `orders`

**Purpose:** Immutable commercial order header plus derived operational status.

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `order_number` | TEXT | No | UNIQUE |
| `user_id` | UUID | No | FK → `users.id` |
| `customer_email_snapshot` | CITEXT | No | verified account email at checkout; STL files are emailed here (ADR-019) |
| `source` | `order_source` | No |  |
| `status` | `order_status` | No | derived projection |
| `fulfillment_method` | `fulfillment_method` | Yes | NULL for digital-only |
| `payment_method` | `payment_method` | No | `online` or `cash`; immutable (ADR-024) |
| `subtotal_cents` | BIGINT | No | CHECK ≥ 0 |
| `tax_cents` | BIGINT | No | Default 0; V1 CHECK = 0 |
| `total_cents` | BIGINT | No | CHECK ≥ 0 |
| `currency` | CHAR(3) | No | CHECK = `USD` |
| `recipient_name` | TEXT | Yes | delivery snapshot |
| `contact_phone_snapshot` | TEXT | Yes | required when `fulfillment_method` is not NULL: the address phone for delivery, entered at checkout for pickup (BR-078); stored normalised to E.164 |
| `contact_phone_hash` | TEXT | Yes | keyed `HMAC-SHA256` of the normalised phone (secret `PHONE_HASH_SALT`, never rotated); set with `contact_phone_snapshot`; used for cash matching |
| `governorate` | TEXT | Yes | delivery snapshot |
| `city` | TEXT | Yes | delivery snapshot |
| `area` | TEXT | Yes | delivery snapshot |
| `street` | TEXT | Yes | delivery snapshot |
| `landmark_notes` | TEXT | Yes | delivery snapshot |
| `customer_note` | TEXT | Yes | customer-visible origin |
| `admin_note` | TEXT | Yes | never customer-visible |
| `estimated_dispatch_at` | TIMESTAMPTZ | Yes | physical orders |
| `terms_accepted_at` | TIMESTAMPTZ | No | consent |
| `digital_terms_accepted_at` | TIMESTAMPTZ | Yes | required when digital lines exist |
| `digital_terms_version` | TEXT | Yes | which digital-terms text was accepted; set exactly when `digital_terms_accepted_at` is (VS-023, ADR-032) |
| `cash_terms_accepted_at` | TIMESTAMPTZ | Yes | required when `payment_method = cash` |
| `placed_at` | TIMESTAMPTZ | No |  |
| `completed_at` | TIMESTAMPTZ | Yes |  |
| `cancelled_at` | TIMESTAMPTZ | Yes |  |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

### Arithmetic Constraint

```text
total_cents = subtotal_cents + tax_cents
```

There is no shipping column: the courier prices and collects the delivery fee (ADR-024).

### Delivery Conditional Constraint

When `fulfillment_method = delivery`, the required address snapshot fields and `contact_phone_snapshot` must be present.

Pickup:

- no address required;
- `contact_phone_snapshot` required.

Digital-only:

- `fulfillment_method IS NULL`;
- address and contact phone not required;
- `payment_method = online`.

```text
fulfillment_method IS NOT NULL → contact_phone_snapshot IS NOT NULL
fulfillment_method IS NULL     → payment_method = 'online'
payment_method = 'cash'        → cash_terms_accepted_at IS NOT NULL
UNIQUE(id, payment_method)     -- target of the composite FKs below
```

As built (VS-023, migration `03a4730dd046`): the delivery fields required are those NOT NULL on `addresses` (`recipient_name`, `governorate`, `city`, `landmark_notes`), and two pair rules hold:

```text
fulfillment_method = 'delivery' → recipient_name, governorate, city, landmark_notes IS NOT NULL
(contact_phone_snapshot IS NULL) = (contact_phone_hash IS NULL)
(digital_terms_accepted_at IS NULL) = (digital_terms_version IS NULL)
```

The fact that an order actually contains physical/digital lines is cross-row and must be validated transactionally; a `cash` order having only physical lines is enforced by the database through the copied `order_items.payment_method` (§8.4).

### Rules

- no guest checkout;
- all amounts are recomputed server-side;
- order number is human-readable;
- status is derived, never independently assigned as business input;
- dispatch estimate uses lead time × `ceil(quantity / batch_size)` across physical lines;
- kill switch stops new checkout only, cash included;
- unpaid online checkout expires according to settings; a cash order has no hold and no payment until its handover;
- order snapshots do not change when the catalogue changes.

### Indexes

```text
(user_id, placed_at DESC)
(status, placed_at DESC)
```

The fulfillment queue excludes `pending_payment` orders (BR-148). The open-cash-order count matches `user_id` or `contact_phone_hash`; add `(contact_phone_hash) WHERE payment_method = 'cash'` if `EXPLAIN` shows the need. The "cash due" admin filter (unpaid cash orders) gets a partial index in VS-029 once `EXPLAIN` shows its shape.

---

## 8.4 `order_items`

**Purpose:** Immutable line-level commercial snapshot and fulfillment state.

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `order_id` | UUID | No | FK → `orders.id` |
| `user_id` | UUID | No | FK → `users.id`; copy of `orders.user_id`, immutable; carries the ownership index |
| `product_id` | UUID | No | FK → `products.id` |
| `offer_id` | UUID | Yes | FK → `offers.id` |
| `product_type` | `product_type` | No | immutable snapshot |
| `product_name_snapshot` | TEXT | No | immutable snapshot |
| `image_snapshot` | TEXT | Yes | immutable snapshot |
| `unit_price_cents` | BIGINT | No | CHECK ≥ 0 |
| `quantity` | INTEGER | No | CHECK > 0 |
| `line_total_cents` | BIGINT | No | CHECK ≥ 0 |
| `currency` | CHAR(3) | No | CHECK = `USD` |
| `fulfillment_status` | `order_item_status` | No |  |
| `lead_time_days_snapshot` | INTEGER | Yes | physical only |
| `batch_size_snapshot` | INTEGER | Yes | physical only |
| `cancelled_at` | TIMESTAMPTZ | Yes |  |
| `fulfilled_at` | TIMESTAMPTZ | Yes | for STL: when marked delivered |
| `delivered_by` | UUID | Yes | FK → `users.id`; STL only: administrator who marked it delivered |
| `payment_method` | `payment_method` | No | copy of the order's; composite FK `(order_id, payment_method)` → `orders(id, payment_method)` |
| `cancel_reason` | `cancel_reason` | Yes | set only with `fulfillment_status = 'cancelled'` from `ready_to_ship`, `returned` or `ready_for_pickup` |
| `receipt_confirmed_at` | TIMESTAMPTZ | Yes | physical only: customer pressed "I got it" (ADR-024) |
| `problem_reported_at` | TIMESTAMPTZ | Yes | physical only: customer reported a problem (ADR-024) |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

### Constraints

```text
line_total_cents = unit_price_cents * quantity
```

STL ownership (INV-18, ADR-019) — at most one live STL line per customer and product. `pending` is included so two parallel checkouts cannot both buy the same STL; a stale unpaid line is cancelled by `release_stale_checkouts`, which frees it:

```text
UNIQUE(user_id, product_id)
WHERE product_type = 'stl'
  AND fulfillment_status IN ('pending', 'awaiting_delivery', 'delivered')
```

Delivery record:

```text
fulfillment_status = 'delivered' AND product_type = 'stl' → fulfilled_at IS NOT NULL AND delivered_by IS NOT NULL
product_type = 'physical' → delivered_by IS NULL
```

Line states by type (VS-023): an STL line is only ever `pending`, `awaiting_delivery`, `delivered`, `refunded` or `cancelled`; a physical line is never `awaiting_delivery`.

For STL snapshots:

```text
product_type = stl → quantity = 1
```

Cash integrity (INV-21):

```text
payment_method = 'cash' → product_type = 'physical'
cancel_reason IS NOT NULL → fulfillment_status = 'cancelled'
```

For physical snapshots:

```text
lead_time_days_snapshot IS NOT NULL
batch_size_snapshot IS NOT NULL AND batch_size_snapshot > 0
```

For STL:

```text
lead_time_days_snapshot IS NULL
batch_size_snapshot IS NULL
```

### Rules

- lines are immutable commercial snapshots after order placement;
- status transitions are controlled by the state machine;
- per-line status is mandatory because mixed orders can resolve differently;
- digital fulfillment is independent of physical fulfillment;
- an STL line is marked `delivered` only from `awaiting_delivery`, by an administrator, after emailing the file (ADR-019);
- physical lines may be self-cancelled only while every physical line of the order is `pending` (before start printing);
- on a cash order, `delivered` / `picked_up` are reached only through the cash handover;
- no physical line of an unpaid online order changes state (BR-148);
- customers see `in_production` as `pending`, and their status history omits it;
- receipt confirmation and problem reports never change `fulfillment_status`;
- STL lines are never self-cancellable.

### Index

```text
(order_id)
(fulfillment_status, order_id) WHERE product_type = 'physical'
(created_at) WHERE product_type = 'stl' AND fulfillment_status = 'awaiting_delivery'   -- STL delivery queue
```

---

## 8.5 `order_status_history`

**Purpose:** Append-only history of order projection and, where used, line-status transitions.

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `order_id` | UUID | No | FK → `orders.id` |
| `order_item_id` | UUID | Yes | FK → `order_items.id` |
| `from_status` | TEXT | Yes | NULL for initial state |
| `to_status` | TEXT | No |  |
| `actor_user_id` | UUID | Yes | FK → `users.id` ON DELETE SET NULL (VS-023, ADR-032); NULL = system |
| `reason` | TEXT | Yes |  |
| `created_at` | TIMESTAMPTZ | No | append-only |

### Rules

- no update/delete in normal business operation;
- system transitions are represented with `actor_user_id = NULL`;
- audit logging also records status transitions.

---

## 8.6 `cash_payment_blocks`

**Purpose:** Removes cash from checkout for a customer, and for any account using the same phone, after a whole cash order was refused or not collected (ADR-024). Owned by Ordering.

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `user_id` | UUID | No | FK → `users.id` |
| `contact_phone_hash` | TEXT | No | copied from `orders.contact_phone_hash`; the plaintext number is never stored here |
| `order_id` | UUID | No | FK → `orders.id`; UNIQUE |
| `reason` | `cancel_reason` | No | CHECK `reason IN ('refused', 'no_show')` |
| `created_at` | TIMESTAMPTZ | No |  |
| `cleared_at` | TIMESTAMPTZ | Yes | set by an administrator |
| `cleared_by` | UUID | Yes | FK → `users.id`; required with `cleared_at` |

### Rules

- inserted, under the phone advisory lock, in the transaction of the cancel that leaves a cash order with no live line, when every line cancelled from `ready_to_ship`, `returned` or `ready_for_pickup` carries `refused` or `no_show` (at least one); never for a partial refusal, an order with any `other` such cancel, or an online order;
- survives account anonymisation without readable personal data, because it holds only the hash;
- cash is unavailable while any uncleared row matches the customer **or** the phone hash;
- cleared, never deleted.

### Indexes

```text
(user_id) WHERE cleared_at IS NULL
(contact_phone_hash) WHERE cleared_at IS NULL
```

---

# 9. Payment and Refund Tables

## 9.1 `payments`

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `order_id` | UUID | No | FK → `orders.id` |
| `provider` | `payment_provider` | No | `mock` in development; `cash` for a recorded cash payment; the online provider per SRS §30.4, chosen at checkout or retry |
| `order_payment_method` | `payment_method` | No | copy of the order's; composite FK `(order_id, order_payment_method)` → `orders(id, payment_method)` |
| `provider_payment_id` | TEXT | Yes | provider reference |
| `status` | `payment_status` | No |  |
| `amount_cents` | BIGINT | No | CHECK ≥ 0 |
| `currency` | CHAR(3) | No | CHECK = `USD` |
| `initiated_at` | TIMESTAMPTZ | No |  |
| `verified_at` | TIMESTAMPTZ | Yes |  |
| `late_captured_at` | TIMESTAMPTZ | Yes | set when money was captured but cannot be applied: an attempt no longer live, a cancelled order, or an amount that does not match (the attempt is then `failed`); the row stays `failed` / `expired` and is refunded automatically (ADR-024) |
| `captured_amount_cents` | BIGINT | Yes | what the provider reported captured, in `captured_currency`: set with `paid` (the exact amount) and on a late capture (any amount, so an overpayment's refund is not capped by `amount_cents`); never on cash (VS-024, migration `00ce1ce252a6`) |
| `captured_currency` | CHAR(3) | Yes | the captured amount's currency, any ISO 4217 code (a non-USD capture is exactly the mismatch it records); only with `captured_amount_cents` (VS-024) |
| `failed_at` | TIMESTAMPTZ | Yes |  |
| `expired_at` | TIMESTAMPTZ | Yes |  |
| `provider_metadata` | JSONB | Yes | provider-specific metadata only |
| `recorded_by` | UUID | Yes | FK → `users.id`; the administrator who recorded a cash payment |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

### Critical Constraint

Only one live payment per order:

```text
UNIQUE(order_id)
WHERE status NOT IN ('failed', 'expired')
```

`partially_refunded` and `refunded` count as live: an already-paid order can never receive a second payment attempt.

At most one cash payment per order (INV-22), and cash only on a cash order (INV-21):

```text
UNIQUE(order_id) WHERE provider = 'cash'
(provider = 'cash') = (order_payment_method = 'cash')
provider = 'cash' → status IN ('paid', 'partially_refunded', 'refunded') AND recorded_by IS NOT NULL AND verified_at IS NOT NULL AND amount_cents > 0
late_captured_at IS NOT NULL → status IN ('failed', 'expired') AND provider <> 'cash'
provider <> 'cash' → recorded_by IS NULL
```

Added by VS-023 (migration `03a4730dd046`):

```text
status IN ('paid', 'partially_refunded', 'refunded') → verified_at IS NOT NULL   -- paid only through verification
status = 'failed' → failed_at IS NOT NULL;  status = 'expired' → expired_at IS NOT NULL
UNIQUE(provider, provider_payment_id)   -- NULLs distinct; one capture never matches two attempts
```

Added by VS-024 (migration `00ce1ce252a6`, additive: both columns nullable, no default):

```text
ck_payments_captured_shape: (captured_amount_cents IS NULL OR captured_amount_cents >= 0)
    AND (captured_currency IS NULL OR captured_currency ~ '^[A-Z]{3}$')
    AND (captured_currency IS NULL OR captured_amount_cents IS NOT NULL)
ck_payments_captured_when:  captured_amount_cents IS NULL
    OR (provider <> 'cash' AND (late_captured_at IS NOT NULL
        OR status IN ('paid', 'partially_refunded', 'refunded')))
```

The cash index is created before the live-payment index, so a second cash payment reports INV-22 by name.

### Rules

- callback/webhook is not proof;
- independent provider verification confirms an online payment;
- an online payment's confirmed amount must equal the order total;
- a cash payment is created only by the cash handover, directly as `paid`, for exactly the sum of live line totals, with at least one live line (ADR-024);
- verification uses the adapter named in `provider`, never the callback URL; an event whose provider differs is stored and ignored;
- no STL delivery before verified online payment; physical production of an online order waits for payment, of a cash order starts at placement;
- reconciliation job handles missed callbacks for online payments only.

### Index

```text
(status, initiated_at)
WHERE status IN ('pending', 'processing')   -- VS-023: reconciliation covers both (VS-024)
(order_id)
(late_captured_at) WHERE late_captured_at IS NOT NULL   -- late captures visible before VS-030
```

Until VS-030 builds refund obligations, the only supported view of late captures is this listing, served by `ix_payments_late_captured` (VS-023, ADR-032 decision 21). Each one also has a `payment.late_capture` audit row with its reason. The automatic refund in the `late_captured_at` row above is VS-030's.

```sql
SELECT id, order_id, provider, amount_cents, status, late_captured_at
FROM payments WHERE late_captured_at IS NOT NULL ORDER BY late_captured_at;
```

---

## 9.2 `webhook_events`

**Purpose:** Durable, idempotent receipt of provider callbacks before asynchronous/independent verification.

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `provider` | TEXT / enum | No |  |
| `provider_event_id` | TEXT | No |  |
| `event_type` | TEXT | Yes |  |
| `payload` | JSONB | No | raw/normalised provider event |
| `signature_valid` | BOOLEAN | Yes | if provider supports signature |
| `provider_payment_id` | TEXT | Yes | the provider reference the event names (VS-023) |
| `payment_id` | UUID | Yes | FK → `payments.id`; resolved at receipt (VS-023, ADR-024 appendix) |
| `received_at` | TIMESTAMPTZ | No |  |
| `processed_at` | TIMESTAMPTZ | Yes |  |
| `processing_error` | TEXT | Yes |  |

### Critical Constraint

```text
UNIQUE(provider, provider_event_id)
```

Duplicate webhook delivery must not apply a payment twice or repeat state transitions.

As built (VS-023): `provider` is the `payment_provider` enum; `octet_length(payload::text) <= 65536`; indexes `(received_at) WHERE processed_at IS NULL` and `(payment_id) WHERE processed_at IS NULL`. An event that is ignored (unknown payment, provider mismatch) or definitively verified gets `processed_at`; only a provider outage leaves it unprocessed.

---

## 9.3 `refunds`

**Purpose:** Tracks a refund obligation from request through settlement.

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `order_id` | UUID | No | FK → `orders.id` |
| `payment_id` | UUID | No | FK → `payments.id` |
| `amount_cents` | BIGINT | No | CHECK > 0 |
| `currency` | CHAR(3) | No | CHECK = `USD` |
| `kind` | `refund_kind` | No | `admin`, `cancellation`, `late_capture` or `chargeback` |
| `reason` | TEXT | No | free text for people; never used to classify a refund |
| `requested_by` | UUID | Yes | FK → `users.id`; NULL only for `kind = late_capture` (created by the system) |
| `approved_by` | UUID | Yes | FK → `users.id` |
| `status` | `refund_status` | No | `pending`, `settled` or `failed` |
| `reissued_at` | TIMESTAMPTZ | Yes | set on a `failed` refund when it is reissued |
| `reissue_of_refund_id` | UUID | Yes | FK → `refunds.id`; the failed refund this one reissues; UNIQUE |
| `excess_cents` | BIGINT | Yes | chargebacks only: amount the bank took beyond the remaining balance; CHECK ≥ 0 |
| `initiated_at` | TIMESTAMPTZ | No |  |
| `settled_at` | TIMESTAMPTZ | Yes |  |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

### Constraints

```text
requested_by IS NULL → kind = 'late_capture'
reissued_at IS NOT NULL → status = 'failed'
kind = 'chargeback' → status = 'settled'
excess_cents IS NOT NULL → kind = 'chargeback'
UNIQUE(payment_id) WHERE kind = 'late_capture' AND status <> 'failed'
```

### Rules

- partial refund supported;
- refund may cover selected lines; there is no shipping component (ADR-024);
- every V1 refund is manual: the administrator pays it in the provider dashboard or in cash and settles it here; the platform never calls a provider refund API;
- a refund of a `cash` payment is capped at the cash recorded;
- only paid lines are refundable (BR-149); a line's refundable amount is `line_total_cents` minus its items in non-failed refunds and in failed refunds not yet reissued, and a cancelled cash line has 0;
- a line becomes `refunded` only when its refund items cover its whole total; a partial refund leaves it in its state; a refund that would empty an unfinished physical line (`pending`, `in_production`, `ready_to_ship`, `shipped`, `ready_for_pickup`) is refused (cancel instead);
- a cancellation refund is the line's remaining balance, and none is created when that is 0;
- a `failed` refund changes no line state and stays owed (in the obligations queue) until reissued; it never counts toward `refunded` status, but an owed one counts as a refund present;
- a `late_capture` refund has no items and no requester, is created automatically, never counts toward the order status, and is exempt from the item-sum check;
- a `chargeback` refund is created already `settled`, split per line, and never enters the obligations queue;
- refund remains a tracked obligation until settled, or until reissued if it failed;
- a fully refunded STL line becomes `refunded` and leaves the delivery queue if not yet sent;
- an unsettled refund blocks account deletion.

### Index

```text
(created_at)
WHERE status = 'pending' OR (status = 'failed' AND reissued_at IS NULL)   -- obligations queue: pending and owed
```

---

## 9.4 `refund_items`

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `refund_id` | UUID | No | FK → `refunds.id` |
| `order_item_id` | UUID | No | FK → `order_items.id` |
| `amount_cents` | BIGINT | No | CHECK > 0 |
| `created_at` | TIMESTAMPTZ | No |  |

### Constraint

A line should appear at most once in the same refund:

```text
UNIQUE(refund_id, order_item_id)
```

Except for `kind = late_capture` (no items), the sum of refund-item amounts must be validated transactionally against `refunds.amount_cents` and against the amount originally paid/refundable. This is a cross-row invariant and is not a simple CHECK.

---

# 10. Fulfillment

## 10.1 `shipping_zones` — removed

Removed by ADR-024. The courier sets and collects the delivery fee, so the platform stores no zones, rates, threshold or shipping snapshot, and there is no governorate-to-zone mapping. Fulfillment owns no tables of its own: line state lives on `order_items`.

---

# 11. Offer / Negotiation Tables

## 11.1 `offers`

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `user_id` | UUID | No | FK → `users.id` |
| `product_id` | UUID | No | FK → `products.id` |
| `status` | `offer_status` | No |  |
| `turn` | `offer_turn` | Yes | terminal states may be NULL |
| `initial_amount_cents` | BIGINT | No | CHECK > 0 |
| `current_amount_cents` | BIGINT | No | CHECK > 0 |
| `agreed_amount_cents` | BIGINT | Yes | CHECK > 0 when present |
| `currency` | CHAR(3) | No | CHECK = `USD` |
| `responds_by` | TIMESTAMPTZ | Yes | inactivity deadline |
| `accepted_at` | TIMESTAMPTZ | Yes |  |
| `checkout_expires_at` | TIMESTAMPTZ | Yes | accepted offer |
| `rejected_at` | TIMESTAMPTZ | Yes |  |
| `cooldown_until` | TIMESTAMPTZ | Yes | rejection cooldown |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

### Critical Constraint

At most one live offer per customer/product:

```text
UNIQUE(user_id, product_id)
WHERE status IN ('awaiting_admin', 'awaiting_customer', 'accepted')
```

### Rules

- only STL products support offers;
- offer floor is configured in settings and validated on submission;
- counter rounds are unlimited;
- each counter changes turn and deadline;
- acceptance freezes price;
- after acceptance only checkout expiry matters;
- acquiring product by another route auto-closes the offer;
- rejection sets cooldown.

The rule “product must be STL” is cross-table and enforced by the offer service.

### Index

```text
(status, responds_by)
```

---

## 11.2 `offer_rounds`

**Purpose:** Permanent append-only negotiation history.

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `offer_id` | UUID | No | FK → `offers.id` |
| `sequence` | INTEGER | No | CHECK > 0 |
| `actor` | enum | No | customer/admin/system as needed |
| `action` | enum | No | submission/counter/accept/etc. |
| `amount_cents` | BIGINT | Yes | CHECK > 0 when present |
| `currency` | CHAR(3) | Yes | if amount present |
| `message` | TEXT | Yes |  |
| `created_at` | TIMESTAMPTZ | No | append-only |

```text
UNIQUE(offer_id, sequence)
```

### Rules

- never update negotiation history;
- never delete negotiation history during normal operations.

---

# 12. Engagement Tables

## 12.1 `reviews`

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `user_id` | UUID | No | FK → `users.id` |
| `product_id` | UUID | No | FK → `products.id` |
| `rating` | SMALLINT | No | CHECK 1..5 |
| `body` | TEXT | Yes |  |
| `is_verified_purchase` | BOOLEAN | No | maintained projection |
| `is_hidden` | BOOLEAN | No | moderation state |
| `deleted_at` | TIMESTAMPTZ | Yes | user/admin soft delete |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

### Critical Constraint

```text
UNIQUE(user_id, product_id)
WHERE deleted_at IS NULL
```

### Rules

- verified user may review without purchase;
- one review per user/product;
- verified-purchase badge depends on a paid, unrefunded order line for the product;
- badge is recomputed when a purchase is paid (online verification or cash handover) or refunded; an unpaid cash line never counts;
- admin may hide/restore;
- rating aggregate on product is recalculated on create/edit/delete/moderation.

---

## 12.2 `wishlist_items`

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `user_id` | UUID | No | FK → `users.id` |
| `product_id` | UUID | No | FK → `products.id` |
| `deleted_at` | TIMESTAMPTZ | Yes | soft-delete marker |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

```text
UNIQUE(user_id, product_id)
WHERE deleted_at IS NULL
```

### Deletion Decision

Wishlist removal follows the SRS blanket soft-delete rule for business entities:

- remove = set `deleted_at`;
- re-add = create/restore one active row;
- product `wishlist_count` counts only active rows.

This keeps wishlist behavior consistent with BR-018 while preserving the normal add/remove user experience.

---

## 12.3 `notifications`

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `user_id` | UUID | No | FK → `users.id` |
| `type` | enum/text | No | notification type |
| `payload` | JSONB | No | type-specific display data |
| `read_at` | TIMESTAMPTZ | Yes | NULL = unread |
| `created_at` | TIMESTAMPTZ | No |  |

### Indexes

```text
(user_id, created_at DESC)
(user_id, created_at DESC) WHERE read_at IS NULL
```

The payload is supporting presentation data, not the source of truth for orders/payments.

---

## 12.4 `custom_requests`

**Purpose:** Bring Your Idea lead workflow; not an online transaction.

VS-034 built this table without `user_id` (the public form ignores auth cookies, so nothing writes it; ADR-030), and with `admin_notes` ≤ 5000 and a currency-with-quote CHECK. See [`docs/custom-requests.md`](../custom-requests.md).

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `user_id` | UUID | Yes | FK → `users.id`; guests allowed |
| `name` | TEXT | No |  |
| `email` | CITEXT | No |  |
| `phone` | TEXT | No |  |
| `project_title` | TEXT | No |  |
| `description` | TEXT | No |  |
| `preferred_material` | TEXT | Yes | lead preference |
| `preferred_colour` | TEXT | Yes | lead preference |
| `dimensions` | TEXT | Yes | lead description |
| `status` | `custom_request_status` | No | Default `new` |
| `quoted_amount_cents` | BIGINT | Yes | CHECK ≥ 0 |
| `currency` | CHAR(3) | Yes | `USD` when quote present |
| `outcome` | enum/text | Yes | won/lost reporting |
| `admin_notes` | TEXT | Yes | private |
| `contacted_at` | TIMESTAMPTZ | Yes |  |
| `quoted_at` | TIMESTAMPTZ | Yes |  |
| `completed_at` | TIMESTAMPTZ | Yes |  |
| `closed_at` | TIMESTAMPTZ | Yes |  |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

### Conditional Money Constraint

```text
quoted_amount_cents IS NULL
OR (quoted_amount_cents >= 0 AND currency = 'USD')
```

### Rules

- guest allowed;
- captcha/rate-limit handled outside DB;
- status follows approved pipeline;
- quote is for lead/funnel reporting: 1 to 100,000,000 cents, set only by the move to `quoted` (ADR-031);
- the server sets `outcome` (`won` at `in_progress`, `lost` at `lost`) and `closed_at` on `closed` or `lost`;
- commercial agreement remains off-platform.

---

## 12.5 `custom_request_attachments`

As built by VS-034 (ADR-030): `scan_status` is the enum `upload_scan_status`, whose only value is `clean` (scanning is synchronous); `storage_key` is a generated `custom-requests/<uuid4>.<ext>` key, unique; `expires_at` is stamped at submission from `custom_request_attachment_retention`.

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `custom_request_id` | UUID | No | FK → `custom_requests.id` |
| `storage_key` | TEXT | No |  |
| `original_filename` | TEXT | No |  |
| `mime_type` | TEXT | No |  |
| `size_bytes` | BIGINT | No | CHECK > 0 |
| `checksum` | TEXT | No |  |
| `scan_status` | enum | No |  |
| `expires_at` | TIMESTAMPTZ | No | purge deadline |
| `created_at` | TIMESTAMPTZ | No |  |

### Rules

- private/admin-only storage;
- content inspection, re-encoding, malware scan happen before trusted use;
- expiry job physically purges file and DB metadata according to explicit retention requirement.

### Index

```text
(expires_at)
```

---

## 12.6 `contact_messages`

VS-033 built this table without `user_id` and `order_id`; VS-029b adds both, as its problem reports are their first writer.

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `user_id` | UUID | Yes | FK → `users.id`; guest allowed |
| `order_id` | UUID | Yes | FK → `orders.id`; set for a customer's problem report (ADR-024) |
| `name` | TEXT | No |  |
| `email` | CITEXT | No |  |
| `phone` | TEXT | Yes |  |
| `subject` | TEXT | Yes |  |
| `message` | TEXT | No |  |
| `status` | `contact_message_status` | No | Default `new` |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

### Index

```text
(status, created_at)
```

---

# 13. Platform Tables

## 13.1 `settings`

**Purpose:** Typed administrator-editable business/operational parameters.

To align with the global UUID primary-key convention, this final design uses a UUID PK and a unique business key.

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `key` | TEXT | No | UNIQUE |
| `type` | enum/text | No | typed validation |
| `value` | JSONB | No | typed value |
| `description` | TEXT | Yes |  |
| `updated_by` | UUID | Yes | FK → `users.id` |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

### Minimum Settings

- accepting-orders kill switch;
- offer response window;
- offer checkout window;
- rejection cooldown;
- minimum offer percentage;
- checkout hold period;
- unverified-account purge period;
- cash payment switch, maximum open cash orders per customer, maximum cash order total (ADR-024);
- pickup address;
- pickup hours;
- WhatsApp number.

### Important Rule

Settings changes are audited.

---

## 13.2 `audit_logs`

**Purpose:** Append-only operational/security/business audit history.

**Partitioning:** monthly range partitions by `created_at`.

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | part of partition-aware PK |
| `actor_user_id` | UUID | Yes | FK → `users.id`; NULL = system/external |
| `action` | TEXT | No | machine-readable action |
| `entity_type` | TEXT | No | target type |
| `entity_id` | UUID | Yes | target identifier |
| `before_data` | JSONB | Yes | redact secrets/PII |
| `after_data` | JSONB | Yes | redact secrets/PII |
| `request_id` | TEXT | Yes | correlation |
| `ip_hash` | TEXT | Yes | where relevant |
| `created_at` | TIMESTAMPTZ | No | partition key |

### Partition Primary Key

```text
PRIMARY KEY (id, created_at)
```

### Audit Coverage

At minimum:

- admin actions;
- authentication events;
- payment events;
- STL line marked delivered;
- order/line status transitions.

### Retention

- 24 months hot;
- then archive according to operations policy.

---

## 13.3 `email_outbox`

**Purpose:** Transactional outbox for reliable customer emails.

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `user_id` | UUID | Yes | FK → `users.id` |
| `recipient_email` | CITEXT | No | immutable destination snapshot |
| `template` | TEXT | No | template identifier |
| `payload` | JSONB | No | render variables |
| `status` | enum/text | No | delivery state |
| `send_after` | TIMESTAMPTZ | No | retry/scheduling |
| `attempt_count` | INTEGER | No | Default 0; CHECK ≥ 0 |
| `last_error` | TEXT | Yes |  |
| `sent_at` | TIMESTAMPTZ | Yes |  |
| `created_at` | TIMESTAMPTZ | No |  |
| `updated_at` | TIMESTAMPTZ | No |  |

### Proposed `outbox_status`

```text
pending
sending
sent
failed
```

### Index

```text
(send_after)
WHERE status = 'pending'
```

### Transaction Rule

The outbox row is inserted **inside the same business transaction** that creates the event requiring the email. Delivery happens after commit.

---

## 13.4 `idempotency_records`

**Purpose:** Stores request identity and response for idempotent operations, especially checkout.

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `user_id` | UUID | Yes | FK → `users.id` |
| `scope` | TEXT | No | e.g. checkout |
| `key` | TEXT | No | client idempotency key |
| `request_hash` | CHAR(64) | No | hash of canonical request |
| `state` | TEXT | No | `in_progress` (first transaction) or `done` (response stored); VS-023 |
| `resource_id` | UUID | Yes | what the claim created, e.g. the order id; no FK, the table is scope-generic (VS-023) |
| `status_code` | INTEGER | Yes | stored HTTP result |
| `response_body` | JSONB | Yes | stored response |
| `expires_at` | TIMESTAMPTZ | No | retention |
| `created_at` | TIMESTAMPTZ | No |  |

### Critical Constraint

PostgreSQL 16 supports `NULLS NOT DISTINCT`. Use:

```text
UNIQUE NULLS NOT DISTINCT (scope, user_id, key)
```

For checkout, `user_id` is non-null in practice because guest checkout is forbidden.

### Replay Rules

- same key + same request hash → return stored response;
- same key + different request hash → conflict (`409`);
- record creation and order/payment creation must be coordinated transactionally;
- same key + same request hash while `in_progress` → `409 IDEMPOTENCY_REQUEST_IN_PROGRESS` naming `resource_id`, never a second order or provider call (VS-023).

As built (VS-023): `state IN ('in_progress', 'done')`; `(state = 'done') = (status_code IS NOT NULL AND response_body IS NOT NULL)`; `status_code` within 100–599; `char_length(key)` within 1–255; records expire 24 h after creation.

### Index

```text
(expires_at)
```

for cleanup.

## 13.5 `ip_hash_salts`

**Purpose:** The current salt of the keyed IP hash (SEC-25, VS-046, [ADR-028](../adr/ADR-028-keyed-monthly-rotated-ip-hashes.md)). Rotated once per UTC month by `rotate_ip_salt`; old salts are deleted in the same transaction.

| Column | Type | Null | Constraint |
|---|---|---:|---|
| `id` | UUID | No | PK |
| `salt` | BYTEA | No | `CHECK (octet_length(salt) = 32)`; generated by `gen_random_bytes(32)` |
| `is_current` | BOOLEAN | No | default `true` |
| `created_at` | TIMESTAMPTZ | No | default `clock_timestamp()` |

`UNIQUE (is_current) WHERE is_current` (`uq_ip_hash_salts_one_current`): at most one current salt.

---
# 14. Relationship / Foreign-Key Catalogue

| Parent | Child | Cardinality | FK | Delete rule |
|---|---|---|---|---|
| users | addresses | 1:N | `addresses.user_id` | CASCADE only on legitimate physical user purge |
| users | sessions | 1:N | `sessions.user_id` | CASCADE |
| users | verification_tokens | 1:N | `verification_tokens.user_id` | CASCADE |
| users | password_reset_tokens | 1:N | `password_reset_tokens.user_id` | CASCADE |
| users | mfa_credentials | 1:0..1 | `mfa_credentials.user_id` | CASCADE only on legitimate physical purge |
| mfa_credentials | mfa_recovery_codes | 1:N | `mfa_recovery_codes.mfa_credential_id` | CASCADE |
| users | carts | 1:1 | `carts.user_id` | CASCADE only on safe purge |
| carts | cart_items | 1:N | `cart_items.cart_id` | CASCADE |
| products | cart_items | 1:N | `cart_items.product_id` | RESTRICT |
| categories | products | 1:N | `products.category_id` | RESTRICT |
| materials | products | 1:N | `products.material_id` | RESTRICT |
| colours | products | 1:N | `products.colour_id` | RESTRICT |
| products | product_images | 1:N | `product_images.product_id` | CASCADE on true purge |
| users | orders | 1:N | `orders.user_id` | RESTRICT; user anonymised instead |
| orders | order_items | 1:N | `order_items.order_id` | RESTRICT |
| products | order_items | 1:N | `order_items.product_id` | RESTRICT |
| offers | order_items | 1:N/optional | `order_items.offer_id` | RESTRICT |
| orders | order_status_history | 1:N | `order_status_history.order_id` | RESTRICT |
| order_items | order_status_history | 1:N optional | `order_status_history.order_item_id` | RESTRICT |
| orders | payments | 1:N | `payments.order_id` | RESTRICT |
| orders | refunds | 1:N | `refunds.order_id` | RESTRICT |
| payments | refunds | 1:N | `refunds.payment_id` | RESTRICT |
| refunds | refund_items | 1:N | `refund_items.refund_id` | RESTRICT |
| order_items | refund_items | 1:N | `refund_items.order_item_id` | RESTRICT |
| users | order_items | 1:N | `order_items.user_id` (ownership copy) | RESTRICT; user anonymised instead |
| users | order_items | 1:N optional | `order_items.delivered_by` | RESTRICT |
| users | payments | 1:N optional | `payments.recorded_by` | RESTRICT |
| users | offers | 1:N | `offers.user_id` | RESTRICT/anonymise |
| products | offers | 1:N | `offers.product_id` | RESTRICT |
| offers | offer_rounds | 1:N | `offer_rounds.offer_id` | RESTRICT |
| users | reviews | 1:N | `reviews.user_id` | RESTRICT/anonymise |
| products | reviews | 1:N | `reviews.product_id` | RESTRICT |
| users | wishlist_items | 1:N | `wishlist_items.user_id` | RESTRICT/anonymise user; wishlist rows soft-delete |
| products | wishlist_items | 1:N | `wishlist_items.product_id` | RESTRICT; wishlist rows soft-delete |
| users | notifications | 1:N | `notifications.user_id` | CASCADE only where retention policy permits |
| users | custom_requests | 1:N optional | `custom_requests.user_id` | SET NULL preferable for guest-like lead preservation |
| custom_requests | custom_request_attachments | 1:N | `custom_request_attachments.custom_request_id` | CASCADE |
| users | contact_messages | 1:N optional | `contact_messages.user_id` | SET NULL preferable |
| orders | contact_messages | 1:N optional | `contact_messages.order_id` | RESTRICT |
| orders | order_items | 1:N | `(order_items.order_id, order_items.payment_method)` → `orders(id, payment_method)` | RESTRICT; cash integrity |
| orders | payments | 1:N | `(payments.order_id, payments.order_payment_method)` → `orders(id, payment_method)` | RESTRICT; cash integrity |
| users | cash_payment_blocks | 1:N | `cash_payment_blocks.user_id` | RESTRICT |
| orders | cash_payment_blocks | 1:0..1 | `cash_payment_blocks.order_id` | RESTRICT |
| users | cash_payment_blocks | 1:N optional | `cash_payment_blocks.cleared_by` | RESTRICT |
| users | audit_logs | 1:N optional | `audit_logs.actor_user_id` | SET NULL if physical purge is ever allowed |
| users | email_outbox | 1:N optional | `email_outbox.user_id` | SET NULL |
| users | idempotency_records | 1:N optional | `idempotency_records.user_id` | CASCADE after expiration/safe purge |

**Note:** Because normal verified-account deletion is anonymisation rather than hard deletion, most user-history FKs should never encounter `ON DELETE` in ordinary operation.

---

# 15. Database-Enforced Invariants

These are the most important constraints to express directly in PostgreSQL.

## 15.1 Identity

- unique live email;
- one active/default address per user;
- unique token hashes;
- at most one MFA credential per user;
- unique recovery-code hashes.

## 15.2 Catalogue

- non-negative price;
- V1 currency = USD;
- physical/STL type-integrity checks;
- one live slug per product;
- one cover image per product;
- rating aggregate 0..5;
- non-negative aggregate counters.

## 15.3 Cart

- one cart per user;
- one line per `(cart, product)`;
- quantity > 0;
- non-negative price snapshot;
- STL line quantity = 1 (`ck_cart_items_stl_quantity_one`), on a type snapshot proven by a composite FK (ADR-029).

## 15.4 Ordering

- unique order number;
- non-negative monetary values;
- total arithmetic;
- tax = 0 in V1;
- STL order-item quantity = 1;
- physical snapshot has lead-time and batch-size;
- delivery requires the address snapshot fields; every physical order requires a contact phone;
- a digital-only order is `online`; a cash order records cash-terms consent;
- a cash order has only physical lines (copied `payment_method` + CHECK);
- a cancel reason only on a cancelled line;
- one cash payment block per order.

## 15.5 Digital Access

- one live STL line per `(user, product)` (§8.4);
- a delivered STL line records when and by whom.

## 15.6 Payments

- one live payment per order;
- a `cash` payment is never `pending` or `processing`, is above zero and records who recorded it;
- at most one `cash` payment per order;
- `provider = 'cash'` exactly on cash orders.
- unique webhook provider event;
- payment/refund money non-negative;
- refund-item amount > 0.

## 15.7 Offers

- one live offer per `(user, product)`;
- positive offer amounts;
- unique round sequence per offer.

## 15.8 Reviews/Wishlist

- rating integer 1..5;
- one active review per `(user, product)`;
- one **active** wishlist row per `(user, product)` via partial unique index.

---

# 16. Invariants That Require Transaction/Application Logic

Not every business rule can be expressed as a local SQL CHECK. These must be implemented in services/use cases with transactions and row locking where necessary.

1. Product name exists before publication.
2. Cart STL quantity is 1 based on the referenced product type.
3. Customer cannot add an STL product they already own (paid, unrefunded line).
4. Physical quantity cannot exceed the product's current max-per-line.
5. Product is visible, non-deleted, available, and permits online purchase at checkout.
6. Offer references an STL product only.
7. Only an administrator marks an STL line delivered, and only from `awaiting_delivery`.
8. STL lines enter `awaiting_delivery` only after independently verified payment.
9. Order status projection matches payment + line states.
10. Cancellation cutoff races against start printing (`pending → in_production`); both lock the order row first, then the lines (ADR-024 lock order).
11. Refund-item totals do not exceed paid/refundable amounts.
12. A refunded STL line leaves the delivery queue in the same transaction.
13. Acquiring an STL through another route auto-closes the live offer.
14. Verified-purchase badge is recomputed when qualifying purchase evidence changes.
15. Product rating/review/wishlist aggregates remain consistent with source rows.
16. Checkout idempotency record, order, lines, and initial payment are coordinated atomically.
17. Address and contact-phone requirements match actual physical-line composition; a `cash` order has only physical lines.
18. Dispatch estimate is calculated from physical order-line snapshots.
19. Kill switch blocks new checkout but not an in-flight payment.
20. Category cannot be archived/deleted while live products remain assigned.
21. Cash checkout respects `cash_payment_enabled`, uncleared blocks for the customer or phone hash, `cash_max_open_orders` for the customer or phone hash, and a **recomputed** total above 0 and within `cash_max_order_total`; checked after the recompute, under the cart lock and an advisory lock on the phone hash.
22. The cash handover requires at least one live line, marks every live line delivered / picked up and creates the single cash payment for exactly their total (above zero), in one transaction under the ADR-024 lock order.
23. A cash refusal or no-show (`ready_to_ship`, `returned` or `ready_for_pickup` → `cancelled`) creates no refund; when a cancel leaves the order with no live line and every such cancelled line carries `refused` or `no_show` (at least one), a `cash_payment_blocks` row is inserted in the same transaction, under the phone advisory lock, independent of cancel order.
24. No physical line of an unpaid online order changes state (BR-148), except the hold release cancelling its `pending` lines; a payment that reached `paid` (`paid`, `partially_refunded`, `refunded`) allows transitions.
24a. A capture on a non-live attempt, a cancelled order, or for a mismatched amount is a late capture: `late_captured_at`, one automatic refund, an alert, no change to the order or lines; a duplicate success for a `paid` attempt is a no-op.
24b. A line is `refunded` only when fully refunded; an unfinished physical line is never refunded in full; a failed refund changes no line state and stays owed until reissued.
24c. The hold release cancels an order only when the provider confirms it unpaid; it skips orders whose check fails or that have an unprocessed webhook event.
25. Refundable amounts, revenue and the badge count only paid lines (BR-149).
26. Every write that changes an order's lines, payment or refunds locks `orders` first, then lines by `id`, then `payments` (ADR-024).

---

# 17. State Machines

## 17.1 Payment

```text
pending -> processing -> paid -> partially_refunded -> refunded
   |          |
   |          -> failed
   -> expired
              -> expired
paid ---------------------------------------> refunded
```

`paid` requires independent server-side payment verification for an online payment. A `cash` payment is inserted directly as `paid` by the cash handover (ADR-024).

## 17.2 Order Projection

```text
online, no payment reached paid:
  cancelled by the hold release   -> cancelled
  otherwise                       -> pending_payment

cash, no payment yet:
  all lines cancelled      -> cancelled
  otherwise                -> in_progress

payment reached paid (paid, partially_refunded, refunded; online or cash):
  all lines cancelled             -> cancelled
  refunds cover all paid money    -> refunded
  all lines refunded              -> refunded
  any refund present              -> partially_refunded
  all lines terminal              -> completed
  otherwise                       -> in_progress
```

Projection is recomputed in the same transaction as payment/line/refund changes, under the ADR-024 lock order. It takes `orders.cancelled_at` as an input. "Refunds cover all paid money" counts non-failed refund records, pending or settled, never `late_capture` refunds; "all lines refunded" means every line fully refunded.

## 17.3 Digital Order Line

```text
pending -> awaiting_delivery -> delivered
awaiting_delivery | delivered -> refunded
pending -> cancelled            # hold release only; frees the ownership index
```

## 17.4 Physical Delivery Line

```text
pending                          # received
  -> in_production               # start printing; internal, no customer notification
      -> ready_to_ship           # finished
          -> shipped
              -> delivered       # cash order: only via the cash handover
              -> cancelled       # unpaid cash line totalling 0 only; reason other
                  -> refunded    # paid only
              -> returned
                  -> shipped
                  -> in_production
                  -> refunded    # paid only
                  -> cancelled   # unpaid cash only; reason refused/other; no refund; may block (§8.6)

pending -> cancelled                         # customer or admin
in_production -> cancelled                   # admin decision
ready_to_ship -> cancelled                   # admin; reason refused/other; cash may block (§8.6)
```

`returned` is not terminal.

## 17.5 Physical Pickup Line

```text
pending -> in_production -> ready_for_pickup -> picked_up -> refunded (paid only)
pending -> cancelled                          # customer or admin
in_production -> cancelled                    # admin
ready_for_pickup -> cancelled                 # admin; reason refused/no_show/other; cash may block (§8.6)
```

On a cash order `ready_for_pickup -> picked_up` happens only via the cash handover.

## 17.6 Offer

```text
awaiting_admin
  -> rejected
  -> accepted -> paid
              -> checkout_expired
              -> auto_closed
  -> awaiting_customer
       -> awaiting_admin
       -> withdrawn
       -> expired

awaiting_admin -> expired
```

Once accepted, the inactivity timer no longer controls the offer; only checkout expiry applies.

## 17.7 Custom Request

```text
new -> contacted -> quoted -> in_progress -> completed -> closed
          \           \
           -> lost     -> lost
```

---

# 18. Search Design

## 18.1 Product Search

`products.search_vector` is generated/stored:

```text
to_tsvector('english', ...)
```

Product name receives higher search weight than description.

## 18.2 Search Indexes

```text
GIN(products.search_vector)
GIN(products.name gin_trgm_ops)
```

Query strategy:

1. full-text search first;
2. trigram fallback when results are thin.

---

# 19. Index Strategy

Indexes are based on known query paths, not “index every column.”

## 19.1 Catalogue

```text
(type, category_id, price_cents)
WHERE deleted_at IS NULL AND is_visible = TRUE

(type, material_id, colour_id, price_cents)
WHERE deleted_at IS NULL AND is_visible = TRUE

(average_rating DESC)
WHERE deleted_at IS NULL AND is_visible = TRUE

(created_at DESC)
WHERE deleted_at IS NULL AND is_visible = TRUE
```

Because active category is also required for storefront visibility, query plans must be checked with the category join.

## 19.2 Product Slug/Search

```text
UNIQUE(slug) WHERE deleted_at IS NULL
GIN(search_vector)
GIN(name gin_trgm_ops)
```

## 19.3 Orders

```text
(user_id, placed_at DESC)
(status, placed_at DESC)
```

## 19.4 Order Fulfillment

```text
(fulfillment_status, order_id)
WHERE product_type = 'physical'
```

## 19.5 STL Delivery Queue and Ownership

```text
order_items(created_at) WHERE product_type = 'stl' AND fulfillment_status = 'awaiting_delivery'
```

plus the unique STL-ownership index on `order_items` (§8.4).

## 19.6 Offers

```text
(status, responds_by)
```

plus the unique live-offer index.

## 19.7 Email Outbox

```text
(send_after)
WHERE status = 'pending'
```

## 19.8 Payment Reconciliation

```text
(status, initiated_at)
WHERE status IN ('pending', 'processing')
```

## 19.9 Pending Refunds

```text
(created_at)
WHERE status = 'pending' OR (status = 'failed' AND reissued_at IS NULL)
```

## 19.10 Notifications

```text
(user_id, created_at DESC)
(user_id, created_at DESC) WHERE read_at IS NULL
```

## 19.10a Cash Payment Blocks

```text
cash_payment_blocks(user_id) WHERE cleared_at IS NULL
cash_payment_blocks(contact_phone_hash) WHERE cleared_at IS NULL
```

## 19.11 Retention Jobs

```text
verification_tokens(expires_at)
password_reset_tokens(expires_at)
sessions(expires_at) WHERE revoked_at IS NULL
custom_request_attachments(expires_at)
idempotency_records(expires_at)
```

---

# 20. Hot Query Catalogue

The schema/indexes must serve these expected high-value paths.

1. Browse visible products by type/category/price.
2. Filter physical products by material/colour/price.
3. Sort catalogue by price, rating, newest.
4. Search product names/descriptions.
5. Autocomplete/fuzzy product names.
6. Load a product with images/reviews summary.
7. Load customer's persistent cart and lines.
8. Check STL ownership for `(user, product)` via the ownership index.
9. List customer's orders newest first.
10. Admin order queue by status/date/customer/fulfillment/payment method, and unpaid cash orders ("cash due").
11. Load order + lines + payment/refund state.
12. Find processing online payments for reconciliation.
13. Find pending refund obligations.
14. Find offers whose response deadline has expired.
15. Find pending email-outbox rows due for delivery.
16. List unread notifications for a user.
17. Admin STL delivery queue: lines awaiting delivery, oldest first.
18. Best-selling STLs from paid, unrefunded order lines.
19. Admin Bring Your Idea queue by status/date.
20. Admin contact-message queue by status/date.

---

# 21. Partitioning and Retention

## 21.1 `downloads`

Removed by ADR-019 (no downloads table).

## 21.2 `audit_logs`

Partition:

```text
RANGE(created_at) by month
```

Retention:

- hot: 24 months;
- then archive according to operations policy.

Operational rule:

- create partitions at least 3 months in advance;
- alert if future partitions are missing.

## 21.3 Other Retention-Managed Records

- expired verification/password tokens: purge `security_token_retention_period` (default 7 days) past `expires_at` (`purge_expired_security_records`, VS-046);
- never-verified accounts: purge after configured period;
- custom-request attachments: purge after `expires_at`;
- idempotency records: purge after `expires_at` (`purge_expired_idempotency_records`, daily, VS-023);
- sessions: purge `session_retention_period` (default 30 days) after the session ended, the earlier of expiry and revocation (VS-046);
- business-history rows: preserve/anonymise instead of normal hard delete.

---

# 22. Historical Snapshot Rules

These values must be copied at transaction time.

## Order Header Snapshots

- fulfillment method;
- payment method;
- recipient/address fields;
- contact phone;
- subtotal/tax/total;
- currency;
- terms-consent timestamps;
- estimated dispatch timestamp.

## Order Line Snapshots

- product ID for traceability;
- product type;
- product name;
- image reference;
- unit price;
- quantity;
- line total;
- currency;
- lead-time days for physical lines;
- batch size for physical lines;
- accepted offer/agreed price when applicable.

### Rule

Later catalogue changes must never alter historical order values.

---

# 23. Delete / Archive / Retention Matrix

| Table | Strategy |
|---|---|
| users | anonymise verified accounts; purge never-verified accounts after configured period |
| addresses | soft delete; physical purge with safe never-verified user purge |
| sessions | revoke + retention purge (`purge_expired_security_records`) |
| verification_tokens | retention purge (`purge_expired_security_records`) |
| password_reset_tokens | retention purge (`purge_expired_security_records`) |
| mfa_credentials | retain while account exists; required for admin; cascade only on legitimate physical purge |
| mfa_recovery_codes | one-time use; old sets invalidated on regeneration; retention purge allowed after security retention |
| categories | soft delete/archive; block while products assigned; release slug |
| materials | soft delete/archive |
| colours | soft delete/archive |
| products | soft delete; release slug |
| product_images | soft delete metadata; physical object garbage-collected only when unreferenced per storage lifecycle |
| carts/cart_items | mutable operational data; cleanup allowed under account/cart lifecycle |
| orders | retain |
| order_items | retain |
| order_status_history | retain append-only |
| payments | retain |
| webhook_events | retention policy may archive/prune after audit period; not specified numerically |
| refunds | retain |
| refund_items | retain |
| offers | retain |
| offer_rounds | retain permanently |
| reviews | soft delete/hide |
| wishlist_items | soft delete; partial unique index permits only one active row |
| notifications | retention policy not numerically specified |
| custom_requests | retain for funnel/history unless retention policy says otherwise |
| custom_request_attachments | physical purge after expiry |
| contact_messages | archive/status; retention not numerically specified |
| settings | retain; changes audited |
| audit_logs | partition + archive after 24 months hot |
| email_outbox | retain through operational/audit retention; exact period not specified |
| idempotency_records | purge after expiry (`purge_expired_idempotency_records`) |
| cash_payment_blocks | retain; cleared, never deleted |

### Wishlist Decision

Resolved for V1: `wishlist_items` uses soft delete with a partial unique active-row constraint. This follows BR-018 while preserving add/remove behavior.

---

# 24. Main Relationship View

```text
USER
 ├── ADDRESS
 ├── SESSION
 ├── VERIFICATION_TOKEN
 ├── PASSWORD_RESET_TOKEN
 ├── MFA_CREDENTIAL
 │    └── MFA_RECOVERY_CODE
 ├── CART
 │    └── CART_ITEM ───────── PRODUCT
 ├── ORDER
 │    ├── ORDER_ITEM ─────── PRODUCT
 │    │    └── REFUND_ITEM
 │    ├── PAYMENT
 │    │    └── REFUND
 │    ├── ORDER_STATUS_HISTORY
 │    └── CASH_PAYMENT_BLOCK
 ├── OFFER ───────────────── PRODUCT
 │    └── OFFER_ROUND
 ├── REVIEW ──────────────── PRODUCT
 ├── WISHLIST_ITEM ───────── PRODUCT
 ├── NOTIFICATION
 ├── CUSTOM_REQUEST
 │    └── CUSTOM_REQUEST_ATTACHMENT
 └── CONTACT_MESSAGE

CATEGORY ───────── PRODUCT
MATERIAL ───────── PRODUCT
COLOUR ─────────── PRODUCT

PRODUCT
 └── PRODUCT_IMAGE

PLATFORM:
SETTING
AUDIT_LOG
EMAIL_OUTBOX
IDEMPOTENCY_RECORD
WEBHOOK_EVENT
```

---

# 25. Critical Concurrency Boundaries

These transactions require explicit locking/atomic constraints.

## Checkout

1. consume/validate idempotency key;
2. check kill switch;
3. lock cart;
4. validate every product;
5. recheck STL ownership;
6. validate current quantities/caps;
7. resolve fulfillment, address and contact phone;
8. recompute totals;
9. validate the payment method and the cash limits against the recomputed total (advisory lock on the normalised phone for cash);
10. create order + lines, and a pending payment (with its chosen provider) for an online order only;
11. calculate dispatch snapshot;
12. clear cart;
13. persist consent;
14. commit.

## Payment Verification

Do not hold DB locks while calling provider.

Transaction A:

- persist webhook if present;
- commit.

External operation:

- verify/query provider.

Transaction B:

- lock the order, then its lines by `id`, then the payment (ADR-024 lock order);
- apply verified state;
- move STL lines to `awaiting_delivery`;
- leave physical lines `pending` (eligible for production);
- close live offer;
- recompute order status;
- write history/audit;
- insert email outbox rows;
- commit.

## Lock Order (ADR-024)

Every write that changes an order's lines, payment or refunds takes its locks in one order: the `orders` row (`FOR UPDATE`), then the lines it reads or changes in `id` order, then the payment row, then recomputes the status. This covers line transitions, self-cancel, admin cancel, the cash handover, payment apply (including late captures), payment retry, reconciliation marking an attempt failed or expired, manual confirmation, refund creation, settlement and failure, chargeback recording, receipt confirmation and problem reports, and `release_stale_checkouts`. **Nothing locks `payments` before `orders`, including batch selection:** a job selects candidate ids without locking (no `FOR UPDATE SKIP LOCKED` on `payments`), then locks each order and re-reads. Locking a line before its order would deadlock against the handover, and two parallel line changes could each derive the order status from a stale view of the other.

## Cancellation vs Start Printing

Self-cancel locks the order, then every physical line, then checks they are all `pending`. Start printing locks the same order row first. Exactly one wins, even when printing starts on a different line from the one the cancel checks last.

## Cash Handover

The handover locks the order row, then all its lines, checks at least one live line, every live line `shipped` / `ready_for_pickup` and the amount equals their total, then marks them delivered / picked up and inserts the single `cash` payment. Two concurrent handovers, or a handover racing a transition or cancel on any line, serialise on the order lock; the unique cash-payment index is the final guarantee against a second cash payment.

## Cash Checkout Limits

The open-cash-order count and the blocks are read under the cart lock, which serialises one customer's checkouts, and a transaction-scoped advisory lock on the phone hash (`pg_advisory_xact_lock`), which serialises cash checkouts from different accounts sharing a phone. A cancel that may insert a block also locks the customer's cart and then takes the advisory lock, after the order and line locks; checkout never locks an existing `orders` row, so this cannot cycle.

## Payment Retry vs Hold Release

Retry locks the order row and re-checks `pending_payment` and `cancelled_at IS NULL` before inserting; the hold release locks the same row. Exactly one wins: a retry never adds a payment to a cancelled order. The hold release cancels only when the provider confirms the attempt unpaid; it skips orders whose provider check fails or times out, or that have an unprocessed webhook event.

## Offer Submission

The partial unique live-offer index is the final race-safe guarantee.

## STL Ownership

The partial unique STL-ownership index on `order_items` is the final race-safe guarantee against buying the same STL twice.

## Mark Delivered vs Refund

Marking an STL line delivered and refunding it both lock the order row, then that line. Exactly one wins, so a refunded line is never marked sent.

## Payment Creation

The partial unique live-payment index is the final race-safe guarantee; for cash, the unique cash-payment index as well.

---

# 26. Database Migration Rules

1. Every schema change uses Alembic.
2. Never manually modify production schema outside an emergency procedure.
3. Review autogenerated migrations.
4. Production changes use expand-contract when old/new code may overlap.
5. Migration recovery strategy is documented:
   - code rollback compatible;
   - fix-forward;
   - restore where necessary.
6. Data migrations must be resumable or safely rerunnable when large.
7. Index creation on large live tables should use PostgreSQL's concurrent strategy where deployment tooling permits.
8. Partition creation is automated and monitored.
9. No application replicas independently running schema migration on startup.

---

# 27. NFR / Scale Design Inputs

Approved targets relevant to the database:

| Requirement | Target |
|---|---|
| Catalogue response | p95 < 500 ms |
| Search response | p95 < 800 ms |
| Checkout | < 2 s excluding provider redirect |
| Concurrent users | 200 without degradation |
| Catalogue scale | 10,000 products without index redesign |
| Database RPO | ≤ 5 minutes |
| Recovery time | ≤ 4 hours |
| Timestamps | UTC mandatory |

### V1 Capacity Planning Envelope

The SRS provides performance targets but not business-volume forecasts. The following are therefore **engineering planning assumptions for schema/index review**, not sales forecasts. Re-estimate after the first 90 days of real production traffic.

| Table | 1-year planning envelope | Basis |
|---|---:|---|
| `products` | 10,000 | Explicit SRS NFR |
| `users` | 50,000 | Conservative planning assumption |
| `orders` | 100,000 | Conservative V1 envelope |
| `order_items` | 300,000 | Assumes ~3 lines/order |
| `notifications` | 1,500,000 | Multiple lifecycle notifications per active customer |
| `email_outbox` | 1,000,000 | Transactional mail across auth/orders/offers |
| `audit_logs` | 5,000,000 | Highest expected append-only table |

### Largest-Table Decision

For T9, the planned largest table at 1 year is:

```text
audit_logs ≈ 5,000,000 rows
```

It already uses monthly partitioning and retention.

### Review Trigger

Re-run capacity/index review if any table reaches **50% of its 1-year envelope earlier than month 6**, or if p95 latency misses the approved NFR.

---

# 28. T9 ERD / Schema Review Checklist

## Keys and Relationships

- [x] Every entity has a primary key strategy.
- [x] Foreign keys are identified.
- [x] `ON DELETE` behavior is defined by relationship category.
- [x] Business-history relationships use restrictive preservation semantics.
- [x] Category deletion is blocked while products are assigned.

## Nullability

- [x] `NOT NULL` is the default.
- [x] Nullable fields have named reasons.
- [x] Delivery address fields are conditionally required.
- [x] Digital-only orders allow no fulfillment/address.
- [x] Guest lead/contact `user_id` is nullable.

## Constraints

- [x] Monetary values have non-negative/positive checks.
- [x] Rating is 1–5.
- [x] Cart has at most one line per product.
- [x] STL ownership uniqueness is defined (ADR-019).
- [x] Live payment uniqueness is defined.
- [x] Live offer uniqueness is defined.
- [x] Live email uniqueness is defined.
- [x] Product/category slug uniqueness is defined.
- [x] Webhook idempotency uniqueness is defined.
- [x] Product physical/STL type integrity is defined.
- [x] Order total arithmetic is defined (no shipping, ADR-024).
- [x] Cash payment and payment-method checks are defined (ADR-024).
- [x] V1 tax = 0 and currency = USD are defined.

## Time and Money

- [x] `TIMESTAMPTZ`/UTC throughout.
- [x] Integer cents used for money.
- [x] Currency stored explicitly.

## Deletion / Retention

- [x] Strategy documented per table/category.
- [x] Account anonymisation preserved.
- [x] Audit partition/archive documented.
- [x] Attachment expiry documented.
- [x] Soft-delete vs explicit purge tension resolved: business records soft-delete/anonymise; explicit retention-managed records may purge.

## Indexes / Query Paths

- [x] Catalogue browse index.
- [x] Faceted filter index.
- [x] Rating/newest indexes.
- [x] Full-text/trigram search indexes.
- [x] Customer order-history index.
- [x] Admin order-queue index.
- [x] Fulfillment queue index.
- [x] STL delivery queue and ownership indexes.
- [x] Offer expiry index.
- [x] Email outbox index.
- [x] Payment reconciliation index.
- [x] Refund obligation index.
- [x] Retention-job indexes.

## Scale

- [x] Catalogue target: 10,000 products.
- [x] Concurrent-user target: 200.
- [x] Audit logs partitioned.
- [x] 1-year capacity envelopes written; planned largest table = `audit_logs` (~5M rows).

## Schema-Freeze Decisions — Resolved

1. **Shipping zones:** superseded by ADR-024 — no zones or shipping amounts; the courier prices and collects delivery.
2. **Capacity:** 1-year planning envelopes recorded; largest planned table is `audit_logs` (~5M).
3. **Implementation enums:** exact V1 values frozen in §3.14.
4. **Wishlist removal:** soft delete with partial unique active-row constraint.
5. **Refresh-token reuse:** session-level `token_version` + hash rotation + reuse detection; no separate token-history table.
6. **Soft-delete tension:** explicit retention-managed data may physically purge; core business history uses soft delete/anonymisation/retention.

**Step 12 schema freeze: COMPLETE.**

---

# 29. Do Not Add to V1 Schema Without a New Requirement

The following are deliberately absent:

- stock quantity;
- product variants;
- subcategories;
- multi-vendor ownership;
- international shipping model;
- shipping zones, rates or shipping amounts (ADR-024);
- courier tracking;
- guest checkout/order customer snapshots for anonymous users;
- product comments;
- STL licensing management;
- tax/VAT engine;
- recommendation-engine tables;
- ERP integration tables.

If one of these is introduced later, update requirements/ERD/database design first, then create the migration.

---

# 30. Step 12 Completion Record

**Status: COMPLETE — V1 DATABASE SCHEMA DESIGN FROZEN**

- [x] ERD agrees with the entity/relationship catalogue.
- [x] Tables and columns are defined.
- [x] PKs and FKs are defined.
- [x] Nullability is defined.
- [x] `ON DELETE` behavior is defined.
- [x] Monetary/time conventions are fixed.
- [x] Database constraints and partial unique indexes are defined.
- [x] Cross-row/transactional invariants are identified separately.
- [x] Deletion/anonymisation/retention strategy is defined.
- [x] Search/FTS design is defined.
- [x] Hot queries and main indexes are defined.
- [x] Audit partitioning is defined.
- [x] Order/address/product snapshots are defined.
- [x] Concurrency boundaries are identified.
- [x] Shipping removed from the platform; cash on delivery modelled (ADR-024).
- [x] 1-year capacity planning envelope is recorded.
- [x] Implementation enums are frozen.
- [x] Wishlist deletion behavior is frozen.
- [x] Refresh-token session/reuse fields are frozen.
- [x] Admin MFA persistence (`mfa_credentials`, `mfa_recovery_codes`) is defined.
- [x] T9 has no unresolved required database-design item.

## What may still change later

Normal future changes such as online payment provider details, token lifetimes, or actual production-volume estimates are **configuration/integration tuning**, not blockers to the V1 database schema. If a future requirement changes the data model, update this document/ERD first and then create an Alembic migration.

## Next Step

Proceed to **Step 13 — API / Interface Design**.
