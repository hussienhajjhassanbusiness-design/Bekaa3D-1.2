# VS-037 — Review Moderation: Implementation Plan

**Status:** DONE on `vs-037-moderation` (not yet merged). Owner answers (2026-10-27): Q1-Q7
accepted as recommended (see §10). Revision 2 below records what the build changed.
**Date:** 2026-10-27
**Planned against alembic head:** `eeed201dcfd2` (`reviews_and_badge_index`, VS-036).
- Derived statically from `revision` / `down_revision` in `migrations/versions/`: one linear
  chain, one head. No file names `eeed201dcfd2` as its `down_revision`, and there are no
  merge revisions.
- This slice adds **no migration** (D1, §4). If Q3 is answered "add the index", the one new
  revision gets `down_revision = "eeed201dcfd2"`. Re-derive the head just before
  `alembic revision`.

**Pre-flight (2026-10-27):** `git fetch`, `git checkout main`, `git pull --ff-only` (already
up to date at `1882a3e`, "Merge pull request #44 … vs-036-reviews"). There are 26 remote
branches. None mentions VS-037 or moderation. `origin/vs-036-reviews` and
`origin/vs-036-schema` are VS-036 (merged). `origin/fix/vs-028-review` is a code review of
VS-028. Highest ADR on `origin/main`: **ADR-044**. This slice appends to it (D11) and takes
no new number.

**Format:** follows [`VS-036-reviews-plan.md`](VS-036-reviews-plan.md). Every `file:line`
below is on `main` at `1882a3e`.

---

## Revision 2 (2026-10-27): as built

**Measured (CP1, §4.2):** 100,000 live reviews (2,000 users x 50 products, 5% hidden), 20 runs
each, on the test container. Unfiltered admin page: Parallel Seq Scan + top-N heapsort, 9-10 ms
p50 and 12-13 ms p95 in SQL; 22-26 ms p50 and 25-36 ms p95 for the whole HTTP route. `user_id` and
`product_id + hidden=false` use their indexes (under 1.5 ms p95). `hidden=true`, `product_id`,
`rating` and `verified` filters are seq scans, 7-17 ms p95. Under the 50 ms trigger: **no
migration**, head stays `eeed201dcfd2`.

**SQL order of one hide (captured):** `SELECT reviews.product_id` (unlocked) → `SELECT … FROM
products … FOR NO KEY UPDATE OF products` → `SELECT … FROM reviews WHERE id = $1 FOR UPDATE` →
`UPDATE reviews SET is_hidden, hidden_at` → `SELECT sum(rating), count(*) … AND deleted_at IS NULL
AND NOT is_hidden` → `UPDATE products SET average_rating, review_count` → `INSERT INTO audit_logs`
(+ the repository's read-back). No `pg_advisory_xact_lock`.

**Deviations from the plan:**
1. §3.2: the hide/restore methods form a new port `ReviewModerationStore` (`product_id_of`,
   `lock_for_moderation`, `set_hidden`, plus `visible_totals` through a new `ReviewTotals` base),
   not additions to `ReviewStore`. That leaves VS-036's fakes untouched. `recompute_rating` now
   types its store as `ReviewTotals` (type only).
2. §3.2: `admin_page` and `live_by_id` are `SqlReviewStore` methods read directly by the router,
   the same as VS-036's `public_page` / `own_page`; no port (no use case behind them).
3. §3.3 / R5: `AdminContext` is imported from `custom_request_pipeline`, not moved.
4. §6.3: the race gate is the **review row** held `FOR UPDATE` from outside, not the product
   row. It is the one lock every racer reaches, including M6's refund hook, which never takes the
   product.
5. §2: 429 is documented on all four routes (the admin router's limit).
6. §6.2 "same transaction" is proven by failure injection: the audit write raises, giving a 500,
   with neither the flag nor the aggregate moved.

**Mutation proofs (each reverted):**
- Review row locked before the product: M1 (hide first) deadlocks, and 6 unit tests fail.
- No state check: 6 tests fail, including M3. State checked on an unlocked read: M3 gives
  `['hidden', 'hidden']`, and both M4 orders fail.
- No recompute, or recompute before the toggle: the hide/restore aggregate test, M1 and M5 fail.
- No `deleted_at` re-check: 4 tests fail (unit and integration), and M2 (delete first) gives
  `['deleted', 'hidden']`.

---

## 0. Decisions this plan takes (summary)

| # | Decision | Where |
|---|---|---|
| D1 | **No migration.** `is_hidden`, `hidden_at` and `ck_reviews_hidden_shape` already exist (`migrations/versions/eeed201dcfd2_reviews_and_badge_index.py:55`; database-design `:1645-1646`). The slice plan says "Model / migration: None" (`vertical-slice-plan.md:1079`). | §4 |
| D2 | **No `-created_at` admin index in V1.** The unfiltered admin list is a top-N sort over live rows, behind a 300/min per-admin limit. The user filter is served by `ix_reviews_user_live`, and product plus `hidden=false` by `ix_reviews_product_visible` (database-design `:1661-1662`). CP1 measures it on 100k seeded rows. If p95 is over 50 ms, one partial index is added in its own reversible revision (Q3). | §4.2 |
| D3 | **Soft-deleted reviews are invisible to moderation.** List, detail, hide and restore treat `deleted_at IS NOT NULL` as missing: **404**, with the same body as an unknown id. `lock_review_for_moderation` returns deleted rows (`engagement/infrastructure/reviews.py:213-216`, no `_LIVE`), so the service re-checks `deleted_at` **after** the row lock. | §3.3, Q1 |
| D4 | **Lock order: product (`FOR NO KEY UPDATE`), then the review row (`FOR UPDATE`). No `R_user`.** This is already ranked in the VS-036 proof as "products → reviews" (`VS-036…plan.md:935`, `:964-965`, `:989`). Hiding never touches the badge (`:458`). | §8.1 |
| D5 | **State check under the row lock.** Hiding a hidden review, or restoring a visible one, gives **409 `INVALID_STATE_TRANSITION`** (`api-endpoints.md:184`, the same code as `custom_request_admin.py:245`), with `is_hidden` in the body. Nothing is written. | §2.3 |
| D6 | **Reason optional, audit only.** `ReviewModerationRequest.reason?` (`api-endpoints.md:1022-1026`): trimmed, whitespace-only becomes null, at most 500 characters, no control characters. It is stored **only** in the audit row (ADR-044 d1, `ADR-044…md:24-26`). No column, **no author notification** in V1, no appeal flow. | §2.3, Q2 |
| D7 | **Aggregates are recomputed in the same transaction** by the existing `recompute_rating` (`application/services/reviews.py:35-40`), exact over live, not-hidden rows (`infrastructure/reviews.py:150-155`). The same as create, edit and delete (VS-036 D7). | §3.3 |
| D8 | **Audit rows:** `review.hidden` / `review.restored`, `entity_type="review"`. `before_data` / `after_data` hold `is_hidden`, `hidden_at`, `product_id` and `reason`. **Never** the body, the author's email or the IP (the IP goes only as `ip_hash` in the writer's own column). Reads are not audited (no PII is shown, Q4). | §3.4 |
| D9 | **Admin schemas show no author identity beyond `user_id`.** The badge is shown both as stored (`is_verified_purchase`, the evidence) and masked (`badge_shown`, what the storefront shows, D14). Keyset on `(created_at, id)` descending. | §2.1 |
| D10 | **Boundary:** a new `admin_router` with `route_class=AdminBoundaryRoute`, mounted on `/api/v1/admin` (`api/v1/admin.py:90-95`). It inherits `require_admin` and `admin_rate_limit`. Writes add `require_csrf`. The OpenAPI-driven matrix picks the four operations up with no edit (`test_deep_vs005_admin_mfa.py:60-81`). | §2, §6.4 |
| D11 | **ADR: append "Decisions recorded in VS-037" (21-27) to ADR-044**, not ADR-045. VS-037 adds no mechanism: it fills in the hide/restore path that ADR-044 d1 and d7 (VS-036 D7) already define, with its audit row (`ADR-044…md:24-26`, `:94`). Q5. | §7 |
| D12 | **The published interface stays as it is.** `engagement.public`'s four review functions (`public.py:139-169`) keep their signatures and semantics, so VS-043, VS-044 and VS-045 are unaffected. VS-037 lives inside Engagement and uses its own ports, not `engagement.public`. | §3.6 |

## 1. Scope and non-goals

### In scope (VS-037 only)

- `GET /api/v1/admin/reviews`, `GET /api/v1/admin/reviews/{review_id}`,
  `POST /api/v1/admin/reviews/{review_id}/hide`, `POST …/restore`
  (`vertical-slice-plan.md:1075-1087`; `api-endpoints.md:629-636`).
- BR-106 "The administrator may hide or restore any review" (`SRS.md:293`); F-101
  (`SRS.md:463`); aggregates "recalculated on … moderation" (`SRS.md:892`; entities
  `:251`, `:990`).
- Audit rows for hide and restore (BR-132, `SRS.md:326`; api-endpoints `:635-636`).

### Non-goals, and who owns them

| Not here | Owner | Why |
|---|---|---|
| Author notification on hide/restore | none in V1 (Q2) | No spec asks for one. `NotificationType` has no review member (`engagement/domain/enums.py`). |
| Appeals | none in V1 | Not in the SRS, entities or api-endpoints. |
| Admin delete of a review | none in V1 | Hide/restore only; history is kept (entities `:993`; VS-036 plan `:99`). |
| Moderating soft-deleted reviews | none | D3: the author's delete is final. VS-044 exports them (`public.py:156-169`). |
| Showing the moderation reason to the author or the public | none | Audit only (D6). |
| Automatic moderation, a report-abuse button | none | The profanity filter is the guardrail (VS-036 plan `:641-642`). |
| Top-rated, export, anonymisation | VS-043 / VS-044 / VS-045 | Interface unchanged (D12). |
| Undo of the author's edit on a hidden review | none | Q4 of VS-036: the author may edit, and it stays hidden (`VS-036…plan.md:1044-1046`). |

---

## 2. API

All routes sit under `/api/v1/admin`, behind `require_admin` and `admin_rate_limit` (300 per
60 s per administrator, `api/v1/admin.py:65-66`, `:90-95`). The answers:
- no session → 401 `AUTH_REQUIRED`;
- customer → 404 `NOT_FOUND`, byte-identical to an imaginary path;
- admin without MFA → 401 `MFA_REQUIRED` (`api/v1/admin.py:16-19`; `api-endpoints.md:104-105`).

Writes add `Depends(require_csrf)` (`identity/api/dependencies.py:153`). A bad or missing
token gives 403. The response maps copy `custom_request_admin.py:62-70` (`_ADMIN_RESPONSES`
401/404; `_WRITE_RESPONSES` adds 403/422), and every route also documents 429.

### 2.1 Schemas (`engagement/api/review_admin_schemas.py`)

```text
AdminReviewRead            # one item; also the detail and the write responses
  id: UUID
  product_id: UUID
  product_slug: str | null   # null when the product is soft-deleted (as MyReviewRead)
  user_id: UUID              # no email, no name (ADR-044 d10)
  rating: int
  body: str | null
  is_verified_purchase: bool # stored evidence (VS-036 plan :464-465)
  badge_shown: bool          # D14 mask: what the storefront shows
  is_hidden: bool
  hidden_at: datetime | null
  created_at: datetime
  updated_at: datetime
  edited: bool

AdminReviewPage  { items: list[AdminReviewRead], next_cursor: str | null }
AdminReviewDetail = AdminReviewRead   # same fields; one schema, two names in OpenAPI
ReviewModerationRequest { reason?: str | null }   # extra="forbid"; ≤ 500; trimmed
```

`AdminReviewDetail` is a subclass with no new fields. It keeps the api-endpoints names
(`:633-636`) without a second shape. The moderation reason is **not** echoed in the
response; the audit log (`/api/v1/admin/audit-logs`) shows it.

### 2.2 `GET /admin/reviews`

- Query:
  - `cursor`, `limit` (default 20, 1-100; the admin precedent, `custom_request_admin.py:52-53`);
  - `hidden: bool?`, `rating: int? (1-5)`, `product_id: UUID?`, `user_id: UUID?`,
    `verified_purchase: bool?` (`api-endpoints.md:633`).
- Rows: live only (`deleted_at IS NULL`, D3), hidden and visible both, newest first:
  `ORDER BY created_at DESC, id DESC`.
- `verified_purchase` filters the **stored** flag. The moderator audits evidence. The
  storefront filter applies the mask (`reviews.py:164-170`). The admin sees both fields
  per row. (Q6)
- Cursor: the VS-036 `created_at|id` base64 cursor (`reviews.py:81-97`), moved unchanged to
  `engagement/api/review_cursor.py` and shared. A tampered cursor gives 422 through
  `invalid_query` (`queue_cursor.py:43-46`). The public cursor bytes do not change; a unit
  test pins that.
- 200 with an empty page for an unknown `product_id` / `user_id`. A filter is not an oracle,
  because the caller is already an MFA-complete admin.

### 2.3 `GET /admin/reviews/{review_id}`, `POST …/hide`, `POST …/restore`

- Detail: an unlocked read of a live row. 404 if the row is missing or deleted.
- Hide / restore:
  - Body `ReviewModerationRequest`, **optional**. A missing body equals `{}`. The OpenAPI
    matrix posts `json={}` (`test_deep_vs005_admin_mfa.py:100`).
  - 200 `AdminReviewDetail` with the new state.
  - 404 `NOT_FOUND` for a missing or soft-deleted review (D3), byte-identical to
    `not_found_error()`.
  - 409 `INVALID_STATE_TRANSITION`, with title "Review is already hidden" / "Review is not
    hidden" and `extensions={"is_hidden": <current>}`.
  - 422 for an unknown field, a reason over 500 characters, or control characters.
  - 403 for CSRF; 429 for the admin limit.
- `hidden_at` is `now` from the route (`datetime.now(UTC)`, as `custom_request_admin.py`
  passes `now`). Restore writes `hidden_at = NULL`. Neither touches `updated_at`, which stays
  the author's edit time (`infrastructure/reviews.py:218-224`). `edited` does not flip on
  moderation.

---

## 3. Layers, function by function

### 3.1 Domain (`engagement/domain`)

- `exceptions.py`: `ReviewModerationConflictError(EngagementDomainError)` carrying
  `is_hidden: bool`. `ReviewNotFoundError` is reused (`exceptions.py:141`).
- `reviews.py`: `MODERATION_REASON_MAX: Final = 500` and
  `normalise_reason(raw) -> str | None` (trim, whitespace-only → None, ValueError over the
  max). Control characters are refused in the schema by `has_control_characters`, the same
  as the body (`review_schemas.py:15-18`), with `allow_line_breaks=False`.

### 3.2 Ports (`engagement/application/ports.py:166-191`, `ReviewStore`)

Four methods are added to the protocol. `SqlReviewStore` already implements two of them.

| Method | Lock | Rows | Status |
|---|---|---|---|
| `product_id_of(review_id) -> UUID \| None` | none | any (deleted included; `product_id` is immutable) | new |
| `lock_for_moderation(review_id) -> Review \| None` | `FOR UPDATE` | any | exists `infrastructure/reviews.py:213-216`; added to the port |
| `set_hidden(review_id, *, hidden, at) -> None` | none (row already locked) | one | exists `:218-224`; added to the port |
| `admin_page(*, hidden, rating, product_id, user_id, verified, after, limit) -> list[Review]` | none | live | new |
| `live_by_id(review_id) -> Review \| None` | none | live | new |

`ReviewableProducts.lock` / `set_rating` are reused as they are (`ports.py:194-…`;
`CatalogReviewableProducts`, `infrastructure/reviews.py:227-237`). The `AuditWriter` port is
`app.platform.application.ports.audit_writer.AuditWriter` (as
`custom_request_pipeline.py:23`).

### 3.3 Application service (`engagement/application/services/review_moderation.py`, new)

```python
async def moderate_review(
    store: ReviewStore,
    products: ReviewableProducts,
    audit: AuditWriter,
    *,
    review_id: UUID,
    hide: bool,
    reason: str | None,
    now: datetime,
    context: AdminContext,
) -> Review:
    """Product lock, then the review row; no `R_user` (plan 8.1). Deleted is missing."""
    product_id = await store.product_id_of(review_id)
    if product_id is None:
        raise ReviewNotFoundError(review_id)
    await products.lock(product_id)
    current = await store.lock_for_moderation(review_id)
    if current is None or current.deleted_at is not None:
        raise ReviewNotFoundError(review_id)
    if current.is_hidden is hide:
        raise ReviewModerationConflictError(current.is_hidden)
    hidden_at = now if hide else None
    await store.set_hidden(review_id, hidden=hide, at=now)
    await recompute_rating(store, products, product_id)
    await audit.record(
        actor_user_id=context.actor_user_id,
        action="review.hidden" if hide else "review.restored",
        entity_type=REVIEW_ENTITY_TYPE,
        entity_id=review_id,
        before_data=_state(current.is_hidden, current.hidden_at, product_id),
        after_data=_state(hide, hidden_at, product_id) | {"reason": reason},
        request_id=context.request_id,
        ip_hash=context.ip_hash,
    )
    return replace(current, is_hidden=hide, hidden_at=hidden_at)
```

- The early 404 (deleted before the call) is safe: deletion is terminal, and there is no
  undelete path. The re-check after the lock covers a delete committed while this
  transaction waited on the product lock. Under READ COMMITTED, `FOR UPDATE` re-reads the
  newest row version.
- `lock` returning `None` is impossible (`fk_reviews_product_id` RESTRICT,
  `eeed201dcfd2…py:48`). The product's `live` / `visible` is **not** checked. A review of a
  product hidden or deleted later is still moderated, and its aggregates still recomputed
  (the same rule as `_lock_own`, `services/reviews.py:69`).
- `AdminContext` is reused from `custom_request_pipeline.py:31-36` (moved to
  `engagement/application/admin_context.py` if the import-direction test objects; it is a
  plain dataclass).
- `_state(is_hidden, hidden_at, product_id) -> dict[str, Any]`:
  `{"is_hidden": …, "hidden_at": iso | None, "product_id": str}`.
- `REVIEW_ENTITY_TYPE = "review"`.

### 3.4 Audit row (D8)

| Field | `review.hidden` | `review.restored` |
|---|---|---|
| `entity_type` / `entity_id` | `"review"` / review id | same |
| `before_data` | `{"is_hidden": false, "hidden_at": null, "product_id": …}` | `{"is_hidden": true, "hidden_at": "<iso>", "product_id": …}` |
| `after_data` | `{"is_hidden": true, "hidden_at": "<iso>", "product_id": …, "reason": str \| null}` | `{"is_hidden": false, "hidden_at": null, "product_id": …, "reason": …}` |
| `actor_user_id`, `request_id`, `ip_hash` | from `AdminContext` | same |

- Excluded on purpose: `body` (customer text, possibly personal), `user_id` of the author
  (reachable through the review id; not needed in the row), email, raw IP.
- The writer never commits (`platform/infrastructure/audit_writer.py:9-13`), so the row
  lands with the toggle and the recompute (BR-132).
- A 404 or 409 writes no audit row (nothing happened).
- The `reason` is admin-typed text. The API docs say not to put personal data in it.

### 3.5 API (`engagement/api/review_admin.py`, new; mounted in `api/v1/admin.py`)

- `admin_router = APIRouter(prefix="/reviews", tags=["admin"], route_class=AdminBoundaryRoute)`,
  copying `custom_request_admin.py:50`.
- `list_reviews`:
  1. Decode the cursor.
  2. `SqlReviewStore(session).admin_page(..., limit=limit + 1)`.
  3. One batched `reviewable_products` (`catalog/public.py`, as `reviews.py:203`) for slug
     and mask.
  4. Build `AdminReviewPage`.
- `read_review`: `live_by_id` → 404 or `AdminReviewDetail`.
- `hide_review` / `restore_review`:
  - `dependencies=[Depends(require_csrf)]`, `claims = Depends(require_admin)`;
  - body `ReviewModerationRequest | None = None`;
  - call `moderate_review(SqlReviewStore(session), CatalogReviewableProducts(session),
    SqlAuditWriter(session), …)`;
  - map `ReviewNotFoundError` → `not_found_error()` and the conflict → 409;
  - then one `reviewable_products` read for the response.
- `_context(request, claims)` is copied from `custom_request_admin.py:73-79`.
- `api/v1/admin.py`: `router.include_router(review_moderation_router)` with a one-line
  `# VS-037` comment, the same as `:113`.
- The commit is owned by `get_session` (`app/api/dependencies.py`), as every admin write.

### 3.6 Published interface (unchanged, D12)

`engagement/public.py:139-169` keeps `recompute_product_rating`,
`lock_review_for_moderation`, `set_review_hidden` and `reviews_for_export` exactly as they
are.
- VS-043 still reads exact aggregates.
- VS-044's export still returns deleted and hidden rows, masked.
- VS-045 still has nothing to blank.

The two moderation helpers stay public for any cross-context caller. VS-037 itself uses the
`ReviewStore` port inside Engagement (`public.py:1-6`: `public` is for *other* contexts).
`tests/unit/test_deep_architecture.py:138-140` still holds, because nothing outside
Engagement imports `engagement.infrastructure`.

---

## 4. Database

### 4.1 Migration: none (D1)

- Writes: `reviews.is_hidden`, `reviews.hidden_at` (through `set_hidden`), and
  `products.average_rating` / `review_count` (through `set_review_aggregates`,
  `catalog/infrastructure/review_aggregates.py:50-59`, which bumps neither `version` nor
  `updated_at`, ADR-020 d5). One `audit_logs` row.
- `ck_reviews_hidden_shape` (`is_hidden = (hidden_at IS NOT NULL)`) is satisfied because
  `set_hidden` writes both columns in one UPDATE. A schema test already covers the
  violation (VS-036 plan `:770`).
- The single head stays `eeed201dcfd2`. Backward compatible: no schema change, no data
  change.

### 4.2 The `-created_at` admin index (D2, Q3)

| Query | Plan with today's indexes |
|---|---|
| `hidden=false, product_id=X` | `ix_reviews_product_visible (product_id, created_at DESC, id DESC) WHERE deleted_at IS NULL AND NOT is_hidden`. Exact match; `NOT is_hidden` bare (ADR-044 d14). |
| `user_id=X` (any `hidden`) | `ix_reviews_user_live (user_id, created_at DESC, id DESC) WHERE deleted_at IS NULL`. Exact match. |
| `product_id=X` with `hidden` unset or true | bitmap on `uq_reviews_user_product_live` is not usable (leading `user_id`); seq scan, top-N |
| no filter / `hidden=true` / `rating` / `verified` | seq scan of `reviews`, top-N heapsort (`LIMIT 21`) |

- **Decision: no index now.**
  - Reviews come one per user per product (D8 of VS-036) at a single shop's scale.
  - The admin list is called by one or a few administrators, capped at 300/min each.
  - A top-N sort keeps 21 tuples in memory, whatever the table size.
  - Every extra index is paid on each customer create, edit and delete and on each badge
    flip.
  - The hidden queue (`hidden=true`) is expected to be tiny. A partial index on it would
    serve almost nothing that a seq scan does not.
- **Measured, not assumed:** at CP1, seed 100,000 live reviews (5% hidden), run
  `EXPLAIN (ANALYZE, BUFFERS)` for the four rows of the table, and record p95 over 20 runs.
- **Trigger:** if the unfiltered page is over **50 ms p95**, add
  `ix_reviews_live_created (created_at DESC, id DESC) WHERE deleted_at IS NULL`. That would
  be one new revision with `down_revision = "eeed201dcfd2"`, `CREATE INDEX` (no data change)
  and a `drop_index` downgrade, plus the matching `Index(...)` in `ReviewModel.__table_args__`
  for the parity test. It is reversible and backward compatible.

---

## 5. Abuse and performance

- **Who can act:** only an MFA-complete administrator (BR-106). Customers get the same 404
  as an imaginary path, so the routes do not exist for them (SEC-10).
- **CSRF** on both writes, and none on reads (the boundary's own rule,
  `api/v1/admin.py:22-23`).
- **Rate:** the admin router limit, per administrator (`api/v1/admin.py:65-66`, `:71-87`). There is no
  slice-specific limit: a hide is cheap and audited.
- **Flip-flop:** repeated hide/restore by an admin is allowed. Each is audited and costs one
  recompute (an index-only range, VS-036 plan `:644`).
- **Oracle:**
  - 404 for missing and for deleted is the same body;
  - 409 only for a live review in the same state, which an admin may know anyway.
- **No PII out:** no email in any response, no body in the audit row (D8, D9).
- **Lock hold time:** product row plus one review row, for one UPDATE and one aggregate
  query. A hide on a product blocks that product's review writes and badge-free aggregate
  writers for milliseconds. It never blocks money paths (the hook never takes products,
  VS-036 plan `:957-958`).
- **Recompute cost:** `visible_totals` is an index-only range on
  `ix_reviews_product_visible` (VS-036 plan `:644-645`).

---

## 6. Tests

[M] = must-have for the checkpoint. [N] = nice-to-have, added if cheap.

### 6.1 Unit (`tests/unit/engagement/test_review_moderation.py`)

Fakes for `ReviewStore`, `ReviewableProducts` and `AuditWriter`, as in `test_review_service.py`.
- [M] Hide records the calls in this order: `product_id_of` → `products.lock` →
  `lock_for_moderation` → `set_hidden(hidden=True, at=now)` → `visible_totals` /
  `set_rating` → `audit.record`. **No `lock_user` call.**
- [M] Restore: the same order, `hidden=False`; `after_data.hidden_at is None`.
- [M] Hide of a hidden review → `ReviewModerationConflictError(is_hidden=True)`. Nothing is
  written after the lock: no `set_hidden`, no `set_rating`, no audit.
- [M] Restore of a visible one → conflict (`is_hidden=False`), the same nothing-written
  checks.
- [M] `product_id_of` → None gives `ReviewNotFoundError`, before any lock.
- [M] The row is deleted under the lock (`deleted_at` set) → `ReviewNotFoundError`, with no
  write and no audit.
- [M] Audit payload: exact `before_data` / `after_data` keys. `body` is absent, and so are
  email and the author's `user_id`. `reason` is carried, or `None`.
- [M] `normalise_reason`: trims, whitespace becomes None, 500 passes, 501 fails.
- [N] The returned `Review` equals the stored row after the write (no stale `is_hidden`).

### 6.2 Integration, real Postgres (`tests/integration/engagement/test_review_moderation_api.py`)

Fixtures from `tests/integration/engagement/review_support.py`, plus an MFA admin
(`mfa_admin`, as in `test_deep_vs005_admin_mfa.py:42`).
- [M] **Hide removes the review from the public list and the aggregates:**
  - three visible reviews (5, 4, 1), so the average is 3.33 and the count 3;
  - hide the 1 → `GET /products/{slug}/reviews` lists two, and the product shows 4.50 / 2;
  - restore → three and 3.33 / 3 again.
- [M] **Same transaction:** after hide, one `SELECT` in a fresh session sees `is_hidden =
  true` and the new aggregate together. A failure injected after `set_rating` (a
  monkeypatched `audit.record` raising) rolls back all three, so the old state and old
  aggregate remain.
- [M] **Repeat hide → 409 `INVALID_STATE_TRANSITION`**, `is_hidden: true` in the body, and
  the aggregates unchanged. **Repeat restore → 409** too.
- [M] **Soft-deleted:**
  - the author deletes, then admin hide → 404, and restore → 404;
  - the body is byte-equal to an unknown id's 404;
  - no audit row, and the aggregates unchanged.
- [M] **Soft-deleted while hidden:** hide, then the author deletes → restore gives 404. The
  row keeps `is_hidden = true` (history kept), and the aggregates exclude it.
- [M] Detail and list exclude deleted rows; detail of a deleted id gives 404.
- [M] `/me/reviews` shows the hidden review with `is_hidden: true`. After restore it shows
  `false`.
- [M] The author edits a hidden review → it stays hidden; the aggregates still exclude it
  (VS-036 Q4 through the moderation path).
- [M] Audit rows: one `review.hidden` and one `review.restored`, with the
  `before_data`/`after_data` of §3.4, `actor_user_id` the admin, and `request_id` set. The
  JSON contains neither the review body nor the author's email (a string search over the
  row).
- [M] List filters, each alone and combined: `hidden`, `rating`, `product_id`, `user_id`,
  `verified_purchase` (stored flag, including on a WhatsApp-only product where
  `badge_shown=false`).
- [M] Keyset: 45 reviews with equal `created_at` on some, pages of 20 → 45 distinct ids, in
  `(created_at, id)` descending order, with no duplicate or gap. A tampered cursor gives 422.
- [M] The response has no `email` key at any depth. `product_slug` is null for a deleted
  product.
- [M] The reason: 501 characters → 422, a control character → 422, an unknown field → 422, no
  body → 200 (reason null).
- [M] Review of a product deleted later: hide succeeds and recomputes. The aggregates on the
  deleted product row are exact.
- [N] `hidden_at` lies within the request window; `updated_at` and `edited` are unchanged by
  hide and restore.

### 6.3 Concurrency, real Postgres (`tests/concurrency/test_review_moderation_races.py`)

**Harness.** The VS-036 harness queues racers on `R_user`
(`tests/concurrency/test_review_races.py:1-3`). Moderation takes no `R_user`, so here the
gate is the **product row**:
1. Hold `SELECT … FROM products WHERE id = :p FOR NO KEY UPDATE` in an outside session.
2. Start racer A and poll `pg_blocking_pids` until A waits.
3. Then start B and wait until B waits.
4. Release.

Postgres grants a tuple lock to queued waiters in arrival order, so A commits first. Each
race runs in **both orders** (swap A and B) and is repeated 20 times. No run may deadlock or
end in a 500.

- [M] **M1 hide vs author edit** (rating 1 → 5):
  - end state `is_hidden = true` with the edited rating;
  - aggregates equal `visible_totals` recomputed from scratch, the hidden row excluded;
  - both return 200.
- [M] **M2 hide vs author delete:**
  - delete first: hide gives 404, no audit row, the row is deleted and not hidden;
  - hide first: hide gives 200, then delete gives 204, the row is deleted and hidden.
  - In both orders the aggregates exclude it.
- [M] **M3 hide vs hide:** exactly one 200 and one 409, one audit row, and the aggregates
  exact.
- [M] **M4 hide vs restore** on a visible review:
  - hide first: 200, then restore 200, ending visible;
  - restore first: 409, then hide 200, ending hidden.
  - The final aggregates match the final state in each order, and the audit rows match the
    200s.
- [M] **M5 aggregates exact under mixed load:**
  - 10 reviews on one product;
  - concurrently: 3 hides, 2 restores (of hidden ones), 2 author edits, 1 author delete and
    1 new create by another user;
  - after all of them, `average_rating` / `review_count` equal a fresh `AVG` / `COUNT` over
    live, not-hidden rows.
- [M] **M6 hide vs badge hook:**
  - a refund of the author's line (the hook takes `R_user` → reviews row) races a hide of
    that review;
  - both orders, no deadlock;
  - the end state has the badge false and `is_hidden` true, and the aggregates are
    unchanged by the badge flip (VS-036 D15).
- [N] M7: hide vs a create of a second review by the same author → 409
  `REVIEW_ALREADY_EXISTS` (a hidden review is live, VS-036 D8), with no deadlock.

### 6.4 Boundary and OpenAPI

- [M] `tests/integration/identity/test_deep_vs005_admin_mfa.py`:
  - the matrix reads the admin paths from `main_app.openapi()` (`:60-81`), so the four new
    operations are covered with **no edit**;
  - anonymous → 401, customer → 404 identical to `IMAGINARY`, admin without MFA → 401
    `MFA_REQUIRED`;
  - wrong methods (for example `DELETE /admin/reviews/{id}`, `GET …/hide`) are picked up by
    `_admin_wrong_methods` (`:70-78`).
  - Run it at CP1 and confirm the count assertion (`:107-108`) still holds.
- [M] `tests/integration/test_openapi_security.py`: a new `VS037_ROUTES` list and a
  parametrised test copied from the VS-029 one (`:125-138`):
  - reads declare `sessionCookie`, writes declare `sessionCookie` + `csrfToken`;
  - `{"401", "404"}` are in the responses, `403` on writes;
  - `409` on hide and restore.
- [M] CSRF: an MFA admin posts hide without the CSRF header → 403, the state is unchanged
  and no audit row is written.
- [M] `tests/unit/test_openapi_snapshot.py:9-13`: regenerate
  `docs/frontend-handoff/openapi.json`. The diff adds only the four operations and the new
  schemas.
- [N] The admin rate limit: the 301st request in a minute → 429, and a customer never sees
  429.

### 6.5 Static

- [M] `tests/unit/test_deep_architecture.py` passes. `engagement/api/review_admin.py`
  imports only Engagement, `app.catalog.public`, `app.identity.public` and
  `app.platform.public`.
- [M] The public cursor bytes are unchanged after the move to `review_cursor.py` (golden
  string).

---

## 7. Docs and ADRs

- **ADR-044, append "### Decisions recorded in VS-037" (21-27)** (D11, Q5):
  - d21 the lock order products → reviews without `R_user`, and why there is no cycle;
  - d22 deleted rows are 404 for moderation;
  - d23 409 `INVALID_STATE_TRANSITION` on a repeat;
  - d24 the reason is audit-only, ≤ 500, with no author notification;
  - d25 the audit payload, with no body or PII;
  - d26 no admin `created_at` index unless CP1 crosses 50 ms;
  - d27 the admin view shows the stored and the masked badge.
  - Add VS-037 to its source basis and "Consequences". Status stays Accepted. The README
    line (`docs/adr/README.md:52`) gains "(VS-036, VS-037)".
  - **Why not ADR-045:** nothing new is chosen at the architecture level. ADR-044 already
    fixes the moderation columns, the exact recompute under the product lock, and "who and
    why goes to VS-037's audit row" (`ADR-044…md:24-26`, `:94`). A separate ADR would split
    one design across two records. If the owner prefers one ADR per slice (the VS-035 /
    ADR-031 precedent), the same seven decisions become ADR-045, which "Amends ADR-044".
- `docs/requirments/api-endpoints.md`:
  - §22 rows `:633-636` gain an "As built (VS-037)" note: 404 for deleted; 409
    `INVALID_STATE_TRANSITION`; CSRF; filters; stored and masked badge; no email.
  - §29.8 adds `AdminReviewRead` / `AdminReviewPage` and fills in `ReviewModerationRequest`
    (`:1022-1026`: ≤ 500, trimmed, optional body).
- `docs/SRS.md`: BR-106 (`:293`) gains "Hide and restore are audited with an optional
  reason; a deleted review cannot be moderated (VS-037)."
- `docs/requirments/database-design.md` §12.1: no change unless the Q3 index is added.
- `docs/vertical-slice-plan.md`:
  - the table row `:42` → Done;
  - the entry `:1075-1087` gains an "As built" block (plan, ADR-044 d21-27, the tests).
- `docs/frontend-handoff/`: `openapi.json` regenerated; one `BACKEND-RESPONSE.md` entry for
  the admin review screens.
- This plan: Status → DONE at the end.

---

## 8. Implementation steps (one PR, no schema)

Each step is small and leaves the tree green. There is **one checkpoint**, at the end.

1. Domain: `ReviewModerationConflictError`, `MODERATION_REASON_MAX`, `normalise_reason`,
   and their unit tests.
2. Ports: add `product_id_of`, `lock_for_moderation`, `set_hidden`, `admin_page` and
   `live_by_id` to `ReviewStore`. Implement the three new ones in `SqlReviewStore`; the
   existing fakes gain stubs.
3. Move the review cursor to `engagement/api/review_cursor.py`; `reviews.py` imports it.
   Add the golden-cursor test.
4. Service `review_moderation.py` (`moderate_review`, `_state`, `REVIEW_ENTITY_TYPE`), and
   the unit tests of §6.1.
5. Schemas `review_admin_schemas.py`; router `review_admin.py` (list, detail, hide,
   restore); mount it in `api/v1/admin.py`.
6. Integration tests of §6.2 and the boundary/OpenAPI tests of §6.4. Regenerate
   `openapi.json`.
7. Races M1-M6 (§6.3), with the product-row gate helper.
8. EXPLAIN measurement at 100k rows (§4.2). Only if it is over 50 ms: the index revision
   (`down_revision = "eeed201dcfd2"`), its parity `Index(...)` and an upgrade/downgrade test.
9. Docs of §7 (ADR-044 d21-27, api-endpoints, SRS BR-106, slice plan, handoff).

**CP1 (owner sign-off, after step 9):**
- pass counts for unit, integration, concurrency (M1-M6 × 2 orders × 20) and the boundary
  matrix;
- the captured SQL order of one hide: `products FOR NO KEY UPDATE` → `reviews FOR UPDATE` →
  `UPDATE reviews` → aggregate `SELECT` → `UPDATE products` → `INSERT audit_logs`, with no
  `pg_advisory_xact_lock`;
- the EXPLAIN table of §4.2 with p95;
- the `openapi.json` diff;
- one sample audit row;
- `alembic heads` = one head.

### 8.1 Lock order and why there is no cycle

The VS-036 ranks are kept unchanged (`VS-036…plan.md:919-946`):
- 7 `R_user`, 8 products, 9 reviews;
- money paths 1-6;
- 10-13 after.

VS-037 hide and restore take **8 → 9 only** (`:935`, `:964-965`). The unlocked
`product_id` read takes no lock.

| Other path | Its locks | Can it close a cycle with 8 → 9? |
|---|---|---|
| Review create / edit / delete | 7 → 8 → 9 (`services/reviews.py:54-55`, `:70-75`) | No. Both take 8 before 9. The one that gets 8 first finishes, and the other waits on 8 holding nothing ranked above it (moderation holds nothing at all; create/edit/delete hold only 7, which moderation never takes). |
| Badge hook (W1-W8) | 2-6 → 7 → 9, **never 8** (`VS-036…plan.md:957-958`; `public.py:116-136`) | No. The hook may hold 9 while moderation waits for 9 with 8 held. The hook then takes only 10-13, never 8, so it never waits on moderation. |
| Wishlist | own row → 8 | No. It holds no 9. |
| Admin product edit | 8 (`FOR UPDATE`) → reference rows | No. It never takes 9. Moderation waits on 8 holding nothing. |
| Another hide/restore | 8 → 9 | Serialised on 8. The second re-reads the row under its own `FOR UPDATE` and sees the new state, so the result is 409 or 200 (M3, M4). |

Every path takes locks in non-decreasing rank, and moderation never holds a rank-9 lock
while it waits for a lower rank. So no cycle exists. M1, M2, M4 and M6 are the runtime
check, and the CP1 SQL capture is the static one.

---

## 9. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | The unfiltered admin list slows as reviews grow | D2: measured at CP1 on 100k rows; the 50 ms trigger adds one reversible partial index |
| R2 | The race harness's ordering assumption (tuple-lock FIFO) is wrong on some run | Both orders are asserted on the end state only; any order must leave exact aggregates and a consistent audit. 20 repeats. |
| R3 | The admin writes personal data into `reason` | Documented in api-endpoints; ≤ 500; audit retention follows the audit policy (VS-046) |
| R4 | `lock_review_for_moderation` returns deleted rows, so another context's caller could moderate a deleted review | D3 guards inside VS-037. The public helper's docstring gains "includes deleted rows; the caller checks `deleted_at`" (docstring only; the signature is unchanged, D12). |
| R5 | `AdminContext` import from `custom_request_pipeline` couples two features | It is moved to `engagement/application/admin_context.py` if the reviewer objects (a plain dataclass) |
| R6 | The author is not told their review was hidden, and may re-post | They cannot: a hidden review is live and blocks a second (409, VS-036 D8). They see `is_hidden: true` in `/me/reviews`. Q2. |
| R7 | The OpenAPI matrix's `len >= 15` assertion or the wrong-method sweep changes count | Only grows. Run at CP1. |

---

## 10. Owner questions

**Answered 2026-10-27:** Q1-Q7 all **as recommended** (404 for deleted; reason audit-only, no
notification; no index unless CP1 > 50 ms p95; reads not audited; append to ADR-044; stored and
masked badge, filter on stored; reuse `INVALID_STATE_TRANSITION`).

1. **Soft-deleted reviews: hide and restore give 404, and they are absent from the admin
   list and detail?**
   *Recommendation:* yes (D3). The author's delete is final, and the row is already
   excluded from every public read and aggregate (`infrastructure/reviews.py:43`, `:150-155`).
   Moderating it would change nothing visible. VS-044 still exports it as deleted.
2. **Reason optional and kept only in the audit row; no notification to the author and no
   appeal in V1?**
   *Recommendation:* yes (D6).
   - `ReviewModerationRequest.reason?` is already optional (`api-endpoints.md:1022-1026`).
   - ADR-044 d1 already sends "who and why" to the audit row (`ADR-044…md:24-26`).
   - No spec asks for a notification (no `NotificationType` exists).
   - The author still sees `is_hidden: true` in `/me/reviews` (`api-endpoints.md:457`).
3. **No `-created_at` admin index now, added only if CP1 measures over 50 ms p95 at 100k
   rows?**
   *Recommendation:* yes (D2, §4.2). Two of the five filters already have exact indexes, and
   a top-N sort is cheap at this scale. Every index taxes the customer write path.
4. **Admin list and detail reads not audited?**
   *Recommendation:* yes. The contact and custom-request queues audit reads because they
   show visitor PII (`custom_request_admin.py:1-2`, `:50-66`). Here no email or name is
   shown, and `user_id` is an opaque id. BR-132 is met by auditing the actions (hide,
   restore).
5. **Append the decisions to ADR-044 (d21-27) rather than open ADR-045?**
   *Recommendation:* append (D11). VS-037 completes a design ADR-044 already fixed. If you
   prefer one ADR per slice, it becomes ADR-045 "Amends ADR-044", with the same content.
6. **The admin view shows the stored badge and the masked badge, and `verified_purchase`
   filters the stored flag?**
   *Recommendation:* yes (D9). The moderator judges evidence, and the VS-036 plan kept the
   unmasked value in `ReviewRow` for this view (`VS-036…plan.md:464-465`). The extra
   `badge_shown` field shows what customers see.
7. **409 code: reuse `INVALID_STATE_TRANSITION`, or add `REVIEW_ALREADY_HIDDEN` /
   `REVIEW_NOT_HIDDEN`?**
   *Recommendation:* reuse (D5). It is the existing catalogue entry for an illegal
   state change (`api-endpoints.md:184`), used by every admin state machine
   (`custom_request_admin.py:245`, `contact_messages.py:246`, `admin_orders.py:307`). The
   body's `is_hidden` tells the client which case it hit.
