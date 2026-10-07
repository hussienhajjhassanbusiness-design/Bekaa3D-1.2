# Catalogue reference data

Categories, materials and colours — the controlled facet values products are
assigned to. Introduced by VS-010.

**V1 is English-only.** Per [ADR-016](adr/ADR-016-english-only-v1.md), which
supersedes ADR-010, catalogue text lives in plain columns on the owning table.
There are no translation tables, no `locale` column, and no fallback logic
anywhere in this slice.

## The three tables

All three share the same lifecycle columns (`database-design.md` §6.1–6.3):

| | `categories` | `materials` | `colours` |
| --- | --- | --- | --- |
| `id` | UUID PK | UUID PK | UUID PK |
| `name` | TEXT NOT NULL | TEXT NOT NULL | TEXT NOT NULL |
| `slug` | TEXT NOT NULL | — | — |
| `is_active` | BOOLEAN NOT NULL, default true | same | same |
| `deleted_at` | TIMESTAMPTZ NULL | same | same |
| `created_at` / `updated_at` | TIMESTAMPTZ NOT NULL | same | same |

Categories have **no hierarchy** — there is no `parent_id`, and V1 has no
subcategories. Materials and colours have **no slug** (they are never addressed
by URL).

Constraints beyond the primary keys:

```sql
-- categories (a9c0aec909a9, then b7e4c1d9a2f6)
UNIQUE(slug)        WHERE deleted_at IS NULL   -- ix_categories_live_slug
UNIQUE(lower(slug)) WHERE deleted_at IS NULL   -- ix_categories_live_slug_ci

-- materials, colours (b7e4c1d9a2f6)
UNIQUE(lower(name)) WHERE deleted_at IS NULL   -- ix_materials_live_name_ci / ix_colours_live_name_ci

-- all three (b7e4c1d9a2f6)
CHECK (deleted_at IS NULL OR NOT is_active)    -- ck_<table>_archived_not_active
```

**Live material and colour names are unique, ignoring case.** `database-design.md`
§6.2/6.3 specifies no such constraint, but SRS §592 gives the reason these are
controlled lists at all: free text "would produce 'PLA', 'pla', and 'PLA
plastic' as three distinct filters". Two live materials called "PLA" and "pla"
reproduce exactly that, so the audit's open question Q-1 was decided in favour
of the SRS. The index is partial, so archiving a value releases its name, the
same as archiving a category releases its slug. Category *names* stay
non-unique; the slug is what identifies a category.

The application already lowercases slugs; `ix_categories_live_slug_ci` makes the
database refuse a case variant from any other writer too (SQL, a future
importer). The CHECK does the same for the rule `archive()` has always
followed: an archived row is never still flagged active.

Migration `b7e4c1d9a2f6` normalises any existing archived-but-active row to
`is_active = false` before adding the CHECK. If live rows already differ only
by case, it **stops before changing anything** and lists each group with its
ids, because choosing which duplicate survives is an administrator's call.
Rename or archive the extras, then rerun the upgrade.

## Three lifecycle states

`is_active` and `deleted_at` are **different states**, not two spellings of one:

```
deleted_at IS NULL  AND is_active        -> live      shown publicly
deleted_at IS NULL  AND NOT is_active    -> disabled  retained, admin-visible,
                                                      hidden publicly, and
                                                      reactivatable via PATCH
deleted_at IS NOT NULL                   -> archived  admin-readable, publicly
                                                      invisible, terminal in V1
```

Keeping "disabled" distinct from "archived" is what lets an administrator take a
category off the storefront temporarily without burning its slug.

`DELETE` archives: it sets `deleted_at` and clears `is_active` in the same
transaction, so a row can never sit in the contradictory "archived but still
flagged active" state. The `ck_<table>_archived_not_active` CHECK enforces that
in the database as well.

**There is no restore endpoint in V1.** Archiving is therefore terminal for the
ordinary admin surface, and an archived row is not editable through `PATCH` — it
answers `409 INVALID_STATE_TRANSITION`. That is the catalogue's existing generic
state-machine code rather than a new one; "requested state-machine transition is
illegal" already describes the situation, and the error catalogue is a contract
rather than a place to add synonyms.

## Slugs

The project had no slug code before this slice, and `database-design.md` gives
`slug` only as `TEXT` with a partial unique index — no pattern, no length. The
rules below are therefore **V1 decisions made in this slice**, not an existing
convention:

- lowercase alphanumerics in hyphen-separated groups: `^[a-z0-9]+(?:-[a-z0-9]+)*$`
- no leading, trailing, or repeated hyphens
- trimmed and lowercased on input
- maximum 200 characters (matching the longest existing string bound in the
  project, `pickup_hours` in the settings registry)

`normalise_slug` is deliberately **not** a slugifier: it will not turn
`"Desk Lamps"` into `"desk-lamps"`. `CategoryCreate` carries an explicit `slug`
alongside `name`, so the administrator chooses the URL; silently rewriting it
would mean the slug they were shown is not the slug that was stored.

### Uniqueness is the database's job

The partial unique indexes are the **only** authority (the exact and the
case-insensitive slug index for categories, the case-insensitive name index for
materials and colours). Creation and renaming attempt the write and translate
PostgreSQL's unique violation into `409 SLUG_CONFLICT`. There is deliberately no `SELECT` to check availability
first: between that read and the insert, another administrator can commit the
same slug, so the check would report "free" for a slug that is about to be
taken. The violation is matched by index name, so an unrelated future constraint
failure is never mis-reported as a slug conflict.

### Archiving releases the slug

The index is partial on `deleted_at IS NULL`, so an archived category drops out
of it in the same transaction and another category may immediately take the
slug — exactly what `database-design.md` §6.1 specifies, with no cleanup step.

## Public endpoints

```
GET /api/v1/categories -> CategoryList  {items: [{id, name, slug}]}
GET /api/v1/materials  -> MaterialList  {items: [{id, name}]}
GET /api/v1/colours    -> ColourList    {items: [{id, name}]}
```

- Public; no authentication.
- Only `deleted_at IS NULL AND is_active = true`.
- Ordered `name ASC, id ASC` — stable, with `id` as tie-breaker because names
  are not unique.
- **Hard limit 100 rows.** `api-endpoints.md` says "hard-limited reference list"
  without a number; 100 is a V1 product decision. These are bounded facet lists,
  not paginated collections, so there is no cursor and no `next_cursor`.
- No `lang`, no search, no filter parameters.

The public schemas expose **only** `id`, `name` and (for categories) `slug`.
That is the second of two independent guards: the query filters to live active
rows, and even if that filter were wrong there is no field for `is_active`,
`deleted_at`, `created_at` or `updated_at` to land in.

### Rate limit

**600 requests/hour/IP, per endpoint**, each with its own counter.

The endpoint catalogue lists `429` for these routes but gives no policy. 600/hour
is the same starting figure adopted for public settings in VS-007, and for the
same reason: these are read on ordinary page loads, so the allowance must be
generous enough that no human browsing reaches it while a scraper does. **A V1
operational decision, not an SRS number.**

## Admin endpoints

All inherit the `/api/v1/admin` boundary — authenticated, administrator,
MFA-complete — so a non-administrator receives the same `404` whether or not the
route exists (SEC-10). Unsafe methods additionally require CSRF (SEC-03).

```
GET    /api/v1/admin/categories            AdminCategoryPage   cursor, ?include_deleted
POST   /api/v1/admin/categories            201 CategoryDetail  409 SLUG_CONFLICT
GET    /api/v1/admin/categories/{id}       CategoryDetail      includes archived
PATCH  /api/v1/admin/categories/{id}       CategoryDetail      409 on archived / slug
DELETE /api/v1/admin/categories/{id}       204                 archives; 409 CATEGORY_IN_USE
                                                               or INVALID_STATE_TRANSITION
```

Materials and colours mirror this without the slug. Their `POST` and `PATCH`
answer `409 SLUG_CONFLICT` when the name matches a live value's name, ignoring
case. The code is reused deliberately rather than adding a `NAME_CONFLICT`:
the error catalogue is a contract, and for a client the situation is the same
one (the identifying value it chose is taken by a live row). The `title` and
`detail` say it was the name.

Admin pages are cursor-paginated: default 20, maximum 100, ordered
`name ASC, id ASC`, with an opaque cursor carrying `(name, id)`. The cursor is
base64 of JSON rather than a delimited string, because a name is arbitrary
administrator text and may contain whatever delimiter looked safe.

Admin reads carry the operational state the public ones omit: `is_active`,
`deleted_at`, `created_at`, `updated_at`.

An empty `PATCH` body is rejected as `422`. A `PATCH` that submits the values
already stored is *not* an error — it is audited with equal before/after and
leaves `updated_at` untouched, following the VS-007 convention.

## Concurrent mutations

`PATCH` and `DELETE` are read-modify-write operations, so both take a row lock
**before** reading anything they act on:

```
SELECT ... FOR UPDATE  ->  check archived  ->  snapshot "before"
                       ->  mutate          ->  save  ->  audit
```

`get_by_id_for_update` (with `execution_options(populate_existing=True)`, so a
cached instance cannot defeat the lock) is used by mutations; `get_by_id` stays
unlocked and serves detail and list reads.

The lock exists to serialise **mutation eligibility and audit truth**. Unlocked,
a `PATCH` and an archive both see `deleted_at IS NULL`, both pass the archived
check, and the loser then mutates a row the winner has already archived —
recording a `before` snapshot of a state that was gone by the time its write
landed. With the lock the second transaction blocks, re-reads the committed row,
and is either correctly refused or proceeds against current data.

**What the lock is not responsible for**, established by break-verifying it
rather than assuming: removing it does *not* let a `PATCH` resurrect an archived
row, and does *not* let two disjoint `PATCH`es erase each other's fields.
SQLAlchemy emits only the columns each transaction actually changed, so a `PATCH`
that never touched `deleted_at` cannot clear it. Those two protections come from
ORM dirty tracking. Different concurrency tests therefore guard different
mechanisms, and only the audit/state-serialisation test turns red when the lock
is removed.

Creation takes no row lock: there is no existing row to lock, and slug
uniqueness is enforced by the partial unique index.

The contract for a `PATCH` racing an archive is that **the row ends archived**,
whichever wins: either the `PATCH` commits first and the archive follows, or the
archive commits first and the `PATCH` is refused with
`409 INVALID_STATE_TRANSITION`. Nothing asserts which request wins.

## Audit

Catalog writes audit records through
`app.platform.application.services.audit_writer.AuditWriter`, Platform's
application-level port — not by importing Platform's infrastructure. That is the
same cross-context discipline as `SettingsReader` and Engagement's
`create_notification`, and `tests/unit/catalog/test_audit_boundary.py` enforces
it. The writer takes the caller's session and never commits.

Every mutation writes an audit row in the **same transaction** as the change, so
a committed mutation without its audit row is impossible, and a failed mutation
leaves no audit row behind.

```
category.created   category.updated   category.archived
material.created   material.updated   material.archived
colour.created     colour.updated     colour.archived
```

`before_data`/`after_data` carry the whole row (`name`, `is_active`,
`deleted_at`, plus `slug` for categories). Reference data contains no PII, so
nothing is redacted.

## The in-use archive guard (VS-013)

A category, material or colour that a **live** product uses cannot be archived:
`DELETE` answers `409 CATEGORY_IN_USE` (BR-013, `database-design.md` §6.1). The
slice plan uses that one code for all three resources. A value used only by
soft-deleted products can be archived; those products keep their reference.
Reassign the live products first (`PATCH /admin/products/{id}`). *Disabling* a
used value (`is_active = false`) stays allowed. It only hides the value publicly.

`products.category_id`, `material_id` and `colour_id` reference these tables
with `ON DELETE RESTRICT`.

**The race.** FR-04 requires that an archive racing a product assignment never
leaves a live product pointing at an archived value. No declarative constraint
can say "no live child references an archived parent", so a lock protocol
enforces it:

- a product create or edit takes `SELECT … FOR SHARE` on every value it newly
  references, and refuses one that is archived or unknown (`422`, on the field);
- archiving takes `SELECT … FOR UPDATE` on the value, then checks for live
  products.

The two locks conflict, so whichever transaction locks first wins and the other
is refused after it commits. `tests/concurrency/test_reference_archive_vs_assignment_race.py`
proves both orders for all three resources, and fails if the `FOR SHARE` is
removed.
