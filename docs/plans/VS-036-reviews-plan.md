# VS-036 — Reviews and Verified Purchase Badge: Implementation Plan

**Status:** DONE. PR A merged (#43; migration `eeed201dcfd2`). PR B (reviews code) built on
`vs-036-reviews`; ADR-044 Accepted (decisions 11-20 record what PR B changed). Profanity list
pending owner review before go-live. Revision 1: the owner answered
Q1-Q10 on 2026-10-25 (Q1, Q2, Q4-Q10 as recommended; Q3: never show the badge on
WhatsApp-only products, keep the purchase data).
**Date:** 2026-10-25
**Planned against alembic head:** `595b7e6e2792` (`orders_customer_cancelled_at`, VS-031).
- Derived statically from `revision` / `down_revision` in `migrations/versions/`: 32
  revisions, one linear chain, one head. No file names `595b7e6e2792` as its
  `down_revision`; no merge revisions.
- This slice's migration (PR A, §4) therefore has `down_revision = "595b7e6e2792"`.
- Re-derive the head immediately before `alembic revision` (nothing else is in flight).

**Pre-flight (2026-10-25):** `git fetch`, `git checkout main`, `git pull --ff-only`
(already up to date at `2dfb27b`, "test(VS-031): close deep-audit findings A-01 to A-05"). 24
remote branches; none mentions VS-036, reviews, ratings or badges. `origin/fix/vs-028-review`
matches "review" only as a code review of VS-028. Highest ADR on `origin/main`: **ADR-043**,
so this slice's ADR is **ADR-044** (re-check before writing it).

**Format:** follows [`VS-024-payment-recovery-plan.md`](VS-024-payment-recovery-plan.md).
Every `file:line` below is on `main` at `2dfb27b`.

---

## Revision 1 (2026-10-25): owner answers and review

**Owner answers (§10).** Q1, Q2 and Q4-Q10 are accepted as recommended. Q3 is decided
differently: **WhatsApp-only products never show the badge**, but the purchase data is
kept (D14).

**What this revision changes:**
1. **Q3, display mask (D14).** `reviews.is_verified_purchase` stays the evidence
   projection, maintained exactly as before. Every read that shows or filters the badge
   uses `badge_shown(stored, purchase_mode) = stored AND purchase_mode IS DISTINCT FROM
   'whatsapp_only'`. If a product switches back to `online_only` / `both`, the badge
   reappears with no write. §2.1, §2.2, §3.1, §3.6 and §6.2 are updated.
2. **Every writer of `order_items.fulfillment_status`** is now listed with file:line,
   including the VS-031 cancellation and chargeback paths, with the hook shown on each
   (§3.2a). The static test is now two [M] tests over the allow-list (§6.1).
3. **Lock order proof**, written as a rank argument (§8.1). Two new [M] real-Postgres
   races: review create against a refund of the same line, and review create against a
   VS-031 cancellation. Each runs in both commit orders (C9, C10, §6.3).
4. **Losing the badge:** only `is_verified_purchase` changes. The aggregates,
   `products.version` / `updated_at` and `reviews.updated_at` stay as they were, and the
   review stays in the public list. New [M] test B-LOSS (§6.2).
5. **The `order_items (user_id, product_id)` lookup** was reasoned through as an EXPLAIN
   against the existing indexes (§4.1a). The physical branch has no serving index, so
   PR A now also adds `ix_order_items_badge_received` (§4.2). R4 is closed.

---

## 0. Decisions this plan takes (summary)

| # | Decision | Where |
|---|---|---|
| D1 | One additive migration: the `reviews` table and one partial index on `order_items` for the badge's physical branch (§4.1a). `products.average_rating` and `review_count` already exist (`catalog/infrastructure/models.py:218-221`, CHECKs `:254-256`), so Catalog needs no schema change. | §4 |
| D2 | The schema PR (PR A) merges first under the migration lock (`CONTRIBUTING.md:20`, `:42`). It has no application code beyond the ORM declarations (`ReviewModel`, and the new `Index` on `OrderItemModel`). | §8 |
| D3 | Moderation state is **both** `is_hidden BOOLEAN NOT NULL DEFAULT false` and `hidden_at TIMESTAMPTZ NULL`, tied by `ck_reviews_hidden_shape` (`is_hidden = (hidden_at IS NOT NULL)`). That satisfies both documents (database-design `:1642`, entities `:956`, `:971`). VS-036 never writes them; VS-037 does. | §4, Q1 |
| D4 | The badge is a **projection recomputed from current line facts**, never toggled by an event. A user has the badge for a product when they hold a line that is either an STL line in `awaiting_delivery` / `delivered` (ownership, ADR-019 d5), or a physical line in `delivered` / `picked_up`. Every other state earns nothing. | §3.1, Q2 |
| D5 | The recompute runs inside Ordering's line-status writers in `ordering/public.py`, after the status UPDATE, in the caller's transaction and under its order-chain locks. A static test makes every caller of a line-state writer call it. | §3.3 |
| D6 | One per-user advisory lock `R_user` serialises badge writers with review creation. Rank: after every order-chain lock (orders, lines, payments, refunds, chargebacks), before the VS-031 cart/phone tail. Review paths take `R_user`, then the product, then the review row, and no order-chain lock. | §8.1 |
| D7 | Aggregates are recomputed **exactly** (`AVG`, `COUNT` over visible rows) under the product row lock (`FOR NO KEY UPDATE`), in the review's transaction. Create, edit, delete, and later VS-037 hide/restore all take that lock, so the last writer always sees every committed review. No deltas. | §3.4 |
| D8 | One live review per user and product: partial unique index `uq_reviews_user_product_live … WHERE deleted_at IS NULL`, mapped to 409 `REVIEW_ALREADY_EXISTS` (`api-endpoints.md:196`). A hidden review is live and blocks a second. A deleted one does not. | §4, §2 |
| D9 | Content rules are a pure domain function: body ≤ 2000 characters after trim, no control characters, no links (URL, `www.`, bare domain, e-mail), and no word from a code-constant profanity list (Q5). Refusal is 422 `REVIEW_CONTENT_REJECTED` with `reason` = `link` or `profanity`. | §5 |
| D10 | Limits are code constants (VS-023/024 precedent): 10 review writes per user per hour, shared by POST, PATCH and DELETE, and the public list at `PUBLIC_RATE_LIMIT` 600/h per IP (`catalog/api/reference_data.py:92-93`). They are not settings. | §5, Q6 |
| D11 | Hook points that change a badge-relevant state: `mark_order_paid` (grants STL), `hand_over_cash_lines` (grants cash physical), `transition_physical_line` (grants online `delivered` / `picked_up`), `refund_lines` (revokes, also on the chargeback path). `cancel_lines`, `cancel_lines_for_chargeback`, `mark_stl_line_delivered` and `release_unpaid_order` call the hook too, for uniformity, and it is provably a no-op there. Fail, void, reissue and settle change no line state, so they need no hook (§3.2). | §3.2 |
| D12 | No author identity is exposed. `users` has no name column (`identity/infrastructure/models.py`: id, email, …), and an email is never shown. VS-045's "author shown as anonymous" therefore needs no write. | §3.6, Q7 |
| D13 | Aggregate writes bump neither `products.version` (ADR-020 d5, `ADR-020…md:21`, `:31`) nor `products.updated_at`, the same as `adjust_wishlist_count` (`catalog/public.py:33-45`). | §3.4 |
| D14 | (Q3, owner) A WhatsApp-only product never **shows** the badge. The stored `is_verified_purchase` still follows the evidence (purchase data kept), and reads apply `badge_shown(...)`. That covers the public list, its `verified_purchase` filter, `/me/reviews` and the VS-044 export. | §3.1, §3.6 |
| D15 | Losing the badge writes `reviews.is_verified_purchase` only. Aggregates count every visible review, verified or not, so they never change on a badge flip. | §3.2, §6.2 |

## 1. Scope and non-goals

### In scope (VS-036 only)

- The `reviews` table, including the moderation columns VS-037 will write (D3).
- `GET /api/v1/products/{slug}/reviews` (public), `GET /api/v1/me/reviews`,
  `POST /api/v1/reviews`, `PATCH /api/v1/reviews/{review_id}`,
  `DELETE /api/v1/reviews/{review_id}` (`docs/vertical-slice-plan.md:1048-1068`,
  `api-endpoints.md:259`, `:456-459`).
- The Verified Purchase badge (BR-102 to BR-104, `SRS.md:289-291`; BR-149 `:344`; INV-17
  `:1152`) and its hook in Ordering's line writers.
- Rating aggregates (SRS §12.2 `SRS.md:890`) through a new Catalog writer.
- Link and profanity filter and rate limit (SRS §12.1 `SRS.md:880-888`).
- The published interface VS-037, VS-043, VS-044 and VS-045 consume (§3.6).

### Non-goals, and exactly who owns them

| Not here | Owner | Why |
|---|---|---|
| `GET/POST /api/v1/admin/reviews…` (list, detail, hide, restore), their audit rows | **VS-037** (`docs/vertical-slice-plan.md:1070-1082`, `api-endpoints.md:628-635`) | VS-036 ships the columns (D3) and `recompute_product_rating` (§3.6), which VS-037 reuses (`:1076`). |
| Top-rated report | **VS-043** (`:1173-1175`) | It reads `products.average_rating` / `review_count` through its own reporting port. |
| Export of a user's reviews | **VS-044** (`:1199`) | It calls `reviews_for_export` (§3.6). |
| Anonymisation | **VS-045** (`:1221`) | No author identity is exposed (D12). It needs no review write. |
| A display name for reviewers | Owner (Q7) | No name column exists. |
| Notifications about reviews | none | No spec asks for one. |
| Admin delete of a review | none in V1 | Moderation is hide/restore only (entities `:987-990`). |
| `refunded_cents_by_line` | **VS-043** (VS-030 plan §3.7) | The badge follows line status, not amounts (§3.1). |

---

## 2. API

All error bodies use the existing problem shape. All routes are under `/api/v1`. Writes need
`current_verified_user` (`identity/api/dependencies.py:119`) and `require_csrf` (`:153`);
an unverified user gets 403 `EMAIL_VERIFICATION_REQUIRED` (same as wishlist,
`engagement/api/wishlist.py:43`).

### 2.1 `GET /products/{slug}/reviews` (public)

- Rate limit: `rate_limiter(key_prefix="reviews_public", limit=PUBLIC_RATE_LIMIT,
  window_seconds=PUBLIC_RATE_WINDOW_SECONDS)`.
- 404 for a non-canonical slug, a missing product, a deleted product or an invisible one. It
  uses the same lookup as `read_product` (`catalog/api/storefront.py:175-180`), exposed as
  `catalog.public.visible_product_id(session, slug)`.
- Query: `cursor`, `limit` (default 20, max 50), `rating` (1..5, optional),
  `verified_purchase` (bool, optional). The sort is fixed at `-created_at, -id`
  (`api-endpoints.md:259`, `:1529-1540`).
- Rows: live (`deleted_at IS NULL`) and not hidden only.
- `200 ReviewPage { items: [PublicReviewRead], next_cursor }`. `PublicReviewRead`: `id`,
  `rating`, `body`, `is_verified_purchase`, `created_at`, `edited` (`updated_at >
  created_at`). It has no user id or email (D12).
- `is_verified_purchase` is `badge_shown(stored, product.purchase_mode)` (D14). For a
  WhatsApp-only product, `verified_purchase=true` returns an empty page and
  `verified_purchase=false` returns every row. The product's mode is read once per request,
  so this adds no per-row join.

### 2.2 `GET /me/reviews` (authenticated)

- `current_user` (unverified allowed: reading your own rows, `api-endpoints.md:456`).
- Query: `cursor`, `limit`. Live rows only, including hidden ones, newest first.
- `200 MyReviewPage { items: [MyReviewRead], next_cursor }`. `MyReviewRead` is
  `PublicReviewRead` plus `product_id`, `product_slug` (null if the product is deleted),
  and `is_hidden` ("own reviews including moderation state"). `is_verified_purchase` is
  masked by D14, using the modes from the same batched `get_many`.

### 2.3 `POST /reviews`

- Body `ReviewCreate { product_id: UUID, rating: int 1..5, body?: str }`
  (`api-endpoints.md:994-1000`).
- Status codes:
  - `201 MyReviewRead`.
  - `404`: the product is missing, deleted or invisible.
  - `409 REVIEW_ALREADY_EXISTS`: a live review exists, hidden or not. The pre-check
    under `R_user`, with the unique index as a backstop (IntegrityError →
    409).
  - `422`: Pydantic validation, or `REVIEW_CONTENT_REJECTED` with `reason`.
  - `429`.
- WhatsApp-only products may be reviewed (BR-100). They never **show** a badge (BR-103,
  Q3 owner answer, D14), even when a past online purchase makes the stored value true.

### 2.4 `PATCH /reviews/{review_id}`

- Body `ReviewUpdate { rating?: int 1..5, body?: str | null }`. At least one field is
  required (422 otherwise). `body: null` clears the text.
- Status codes:
  - `200 MyReviewRead`.
  - `404`: not found, someone else's, or deleted (never 403, so ids cannot be probed).
  - `422`, `429`.
- The badge is recomputed in the same transaction (cheap, and it heals any drift). A hidden
  review stays hidden after an edit (Q4).

### 2.5 `DELETE /reviews/{review_id}`

- `204`; `404` as in PATCH; `429`. Soft delete: `deleted_at = now()`. Repeating it gives 404.
- The user may then post a new review for the product (D8).

### 2.6 Error codes added

`REVIEW_ALREADY_EXISTS` (already in the catalogue at `api-endpoints.md:196`) and
`REVIEW_CONTENT_REJECTED` (new, 422, `reason` ∈ {`link`, `profanity`}). The OpenAPI and
`docs/frontend-handoff/BACKEND-RESPONSE.md:425` are updated (§7).

---

## 3. Layers, function by function

### 3.0 Package ownership

- **Engagement** owns `reviews` (database-design §12 "Engagement Tables", `:1632`), beside
  wishlist.
- **Ordering** owns the badge evidence (it owns `order_items`).
- **Catalog** owns the aggregate columns.
- Import edges:
  - Engagement → Catalog exists.
  - Ordering → Engagement exists (`ordering/infrastructure/notices.py:7`).
  - **New:** `engagement/api/reviews.py` → `ordering.public`, for the evidence read on
    create and edit.
- `engagement/public.py` must not import Ordering (that would be an import cycle). A
  unit test asserts it (§6.1).

### 3.1 Pure rules (`app.engagement.domain.reviews`, `app.ordering.domain.badge`)

```python
# ordering/domain/badge.py
BADGE_STATES: Final = {ProductType.STL: OWNED_STATES, ProductType.PHYSICAL: RECEIVED}
def line_earns_badge(product_type: ProductType, status: OrderItemStatus) -> bool
```

Why status alone is enough, with no Payments read and no cross-context join:

- **STL `awaiting_delivery` / `delivered`.** Only `mark_order_paid` moves an STL line out
  of `pending` (`ordering/public.py:229-241`). Ownership is "a paid, unrefunded STL line"
  (ADR-019 d5 `ADR-019…md:20`; `stl_owned` `ordering/public.py:541-543`; `OWNED_STATES`
  `ordering/infrastructure/orders.py:35`).
- **Physical `delivered` / `picked_up`** (`RECEIVED`, `orders.py:39`):
  - An online line cannot move without a paid payment: `PAYMENT_REQUIRED`,
    `line_transitions.py:104-105`.
  - A cash line reaches those states only through the handover (`CASH_HANDOVER_REQUIRED`
    for `HANDOVER_TARGETS`, `:50`, `:112-113`). The handover records the cash payment
    in the same transaction (`hand_over_cash_lines`, `ordering/public.py:466-469`).
  - So these states imply BR-149's "payment reached paid", and "cash only after the
    handover" (BR-102) follows.
- **Every other state earns nothing** (the full enum is in `ordering/domain/enums.py:42-56`):
  - `pending`, `in_production`, `ready_to_ship`, `shipped` and `ready_for_pickup`: not
    received (Q2: BR-149 alone would also badge a paid online line still in production).
  - `returned`: only reachable from `shipped` (`line_transitions.py:42-43`), so the item
    never reached the customer.
  - `cancelled`: never paid, or its balance went back (ADR-043 d1), or a chargeback
    emptied it (ADR-042 d17).
  - `refunded`: covered in full (`docs/refunds.md:30`).
- **Partial refunds keep the badge.** A partial refund leaves the line in its state
  (`refunds.md:30`), so the line is still "non-refunded".
- **Failed refund.** The line was already `refunded` at creation and stays `refunded` while
  the money is owed (ADR-042 d1, `refunds.md:26`). No badge, and nothing changes.
- **Voided refund.** A void is refused when the line is `refunded` or `cancelled`
  (ADR-042 d23, `refunds.md:65`), so a void never reopens a line, and a void of a partial
  refund leaves the state alone. Nothing changes.
- **Chargeback.** Lines it empties become `refunded` (delivered, picked up, returned,
  STL) or `cancelled` (unfinished physical) (ADR-042 d17). Absorbed refunds never reopen a
  line (d16). The badge is lost exactly when a received line is emptied.

```python
# engagement/domain/reviews.py
RATING_MIN, RATING_MAX: Final = 1, 5
BODY_MAX: Final = 2000
class ContentRefusal(StrEnum): LINK = "link"; PROFANITY = "profanity"
def normalise_body(raw: str | None) -> str | None          # strip; "" -> None
def content_refusal(body: str | None) -> ContentRefusal | None
def rating_average(ratings_sum: int, count: int) -> Decimal  # ROUND_HALF_UP to 0.01; 0 when count=0
def badge_shown(stored: bool, purchase_mode: PurchaseMode | None) -> bool
    """D14 (Q3): a WhatsApp-only product never shows the badge; the stored fact is kept."""
```

`purchase_mode` is `None` for STL products (`catalog/domain/enums.py:11-16`; physical
only), so STL is never masked.

- `content_refusal` runs NFKC + casefold, then:
  - Link patterns: a scheme (`[a-z][a-z0-9+.-]*://`), `www.`, an email address, and
    `label.tld` for a TLD in `LINK_TLDS` (a constant: com, net, org, io, co, me, app, info,
    biz, lb, xyz, link, ly, gg, to).
  - Profanity: whole-word match against `PROFANITY_WORDS` (a frozenset in
    `engagement/domain/profanity.py`, English plus Arabic and Arabizi; Q5).
  - Control characters use `has_control_characters(allow_line_breaks=True)`
    (`core/text.py:26`); they are a 422 validation error, not a content refusal.

### 3.2 The badge hook: where it runs and why there

- **The function.** `ordering/public.py` gains `_refresh_review_badges(session, locked,
  line_ids)`. Each writer below calls it **after** its status UPDATE and history rows. It
  collects `{(line.user_id, line.product_id)}` for the touched lines and calls
  `engagement.public.refresh_review_badges(session, user_id=…, product_ids=…,
  evidence=…)`. An order has one customer (ADR-042 d6, `fk_order_items_order_owner`),
  so `user_id` is the same for every touched line.
- **`evidence`.** A callable bound to `SqlOrderStore(session).badge_product_ids(user_id,
  product_ids)`. That is one query over `order_items` by `(user_id, product_id)`, with the
  §3.1 predicate. It reads this transaction's own uncommitted writes.

### 3.2a Every writer of `order_items.fulfillment_status`, with its hook

**How the list was found.** The search was `grep` over `src/` for `update(_I)` /
`update(OrderItemModel)`, `insert(_I)`, raw `UPDATE order_items`, and every
`fulfillment_status=` / `"fulfillment_status":` assignment.
- **No raw SQL writes.**
- **Excluded hits:**
  - `ordering/infrastructure/carts.py:107-140` writes `cart_items` (`_I` is
    `CartItemModel` there).
  - `payments/infrastructure/refunds.py:118` and `chargebacks.py:91` insert
    `refund_items` / `chargeback_items`.
  - `orders.py:266`, `:277` are VS-029b's receipt stamps (timestamps only, per the
    allow-list comment at `test_order_item_writers.py:19-21`).
  - Migrations are not runtime writers.

**Layer 1: the store methods that write the column** (`ordering/infrastructure/orders.py`).
This is exactly `KNOWN_WRITERS` at `tests/unit/ordering/test_order_item_writers.py:13-22`:

| Store method | Line of the UPDATE / INSERT | Writes |
|---|---|---|
| `insert_lines` | `:133`, value `:142` | new rows (`pending`); **no hook**, a new line never earns (checkout) |
| `set_line_status` | `:248`, `:257-260` | any status, by id list |
| `set_line_delivered` | `:284`, `:287-294` | STL `awaiting_delivery → delivered` |
| `move_line` | `:302`, `:312-318` | one line `from → to` (guarded) |
| `cancel_order_lines` | `:348`, `:353-360` | lines → `cancelled` with reason (guarded) |

**Layer 2: the only callers of those four state writers** (all in `ordering/public.py`).
The hook goes here, after the store call and its history rows, still inside the caller's
transaction:

| # | Public writer | Store call | Callers (every runtime path) | Badge effect | Hook |
|---|---|---|---|---|---|
| W1 | `mark_order_paid` `:229` | `set_line_status` `:239` | online payment applied (webhook, verify job, reconcile) or manual confirm, all through `apply_result` → `ordering_side.py:46`. Record-capture is a late capture and never calls it. | STL `pending → awaiting_delivery`: **grants** | `_refresh_review_badges(session, locked, stl_ids)` after `:241-250` |
| W2 | `cancel_lines` `:310` | `cancel_order_lines` `:323` | **VS-031:** customer cancel, admin order cancel, admin line cancel (`fulfillment/application/cancel_lines.py:59`, `:71`, `:80` → `_cancel` `:126` → `fulfillment/infrastructure/delivery_side.py:118`) | unfinished physical only (ADR-043 d1, d5): no change | after the history rows `:327-339` |
| W3 | `mark_stl_line_delivered` `:342` | `set_line_delivered` `:362` | VS-023b mark-as-sent (`delivery_side.py:73`) | both states earn: no change | after the history row |
| W4 | `transition_physical_line` `:394` | `move_line` `:421` | VS-029 / VS-031 admin transition, incl. `shipped → returned`, `returned → shipped / in_production` (`delivery_side.py:89`) | `→ delivered` / `→ picked_up` **grants**; others none | after `:424-434`, before the recompute |
| W5 | `hand_over_cash_lines` `:466` | `move_line` `:483` | VS-029 cash handover (`delivery_side.py:104`) | live physical → `delivered` / `picked_up`: **grants** | after the loop's history rows |
| W6 | `refund_lines` `:546` | `set_line_status` `:559` | **admin refund create** (`payments/application/services/refunds.py:274` via `refund_side.py:45`); **VS-031 cancellation refund** (`create_cancellation_refund`, `payments/public.py:146-161` → the same refunds service; lines in `cancelling` are excluded, so it is usually empty); **chargeback** emptied received lines (`refund_side.py:64`, from `services/chargebacks.py:237`) | covered line → `refunded`: **revokes** if it was the last earning line | after `:560-572` |
| W7 | `cancel_lines_for_chargeback` `:575` | `set_line_status` `:587` | chargeback emptied unfinished physical lines (`refund_side.py:73`) | no change | after `:588-600` |
| W8 | `release_unpaid_order` `:603` | `set_line_status` `:623` | VS-024 hold-release job and admin release (`payments/infrastructure/release.py:247`, `:332`) | unpaid `pending` lines: no change | after its history rows |

Fail, void, reissue and settle call none of W1-W8 (§3.1), so they need no hook.

**The VS-031 cancellation path, step by step.**
1. `_cancel` (`fulfillment/application/cancel_lines.py:105`) locks orders and lines.
2. `deps.payments.cancellation_refund` (`:117`): payments, then the refund INSERT, and
   W6 for nothing (every cancelled line is in `cancelling`).
3. `deps.orders.cancel` (`:126`) → W2, whose hook takes `R_user`.
4. Only for a cash refusal: `insert_cash_block` (`:142`), so cart → phone.
5. The recompute (`:145`).

`R_user` is therefore taken after refunds and before cart and phone (§8.1).

### 3.2b Hook mechanics

- **Why the hook sits in the writers, not in the VS-030 refund use cases.** The VS-030
  plan's list (`VS-030-refunds-settlement-plan.md:171`, `:698`) names `create_refund`,
  `void_refund`, `fail_refund`, `reissue_refund` and `record_chargeback`.
  - Fail, void, reissue and settle never write `order_items` (§3.1). Hooking them would be
    dead calls.
  - Create and chargeback reach the badge only through `refund_lines`, so the writer-level
    hook covers them.
  - It also covers the paths the slice text lists (payment, handover, `:1055`) and the one
    it misses (the online physical delivery under D4).
  - The rule "every writer of a line state calls the hook" is enforced statically (§6.1),
    beside `KNOWN_LINE_STATUS_CALLERS` (`tests/unit/ordering/test_order_item_writers.py:24-29`).
- **`refresh_review_badges` (Engagement), in order:**
  1. `pg_advisory_xact_lock(REVIEW_LOCK_NS, hashtext(user_id::text))`: the per-user lock
     `R_user`. It is re-entrant, so two hooks in one transaction (VS-031: `refund_lines`,
     then `cancel_lines`) are fine.
  2. `SELECT id, product_id FROM reviews WHERE user_id = :u AND product_id = ANY(:p) AND
     deleted_at IS NULL ORDER BY id FOR UPDATE`. If it finds nothing, return. That is the
     normal case on payment paths: no evidence query and no write.
  3. `true_ids = await evidence(found_product_ids)`.
  4. `UPDATE reviews SET is_verified_purchase = (product_id = ANY(:true_ids)) WHERE id =
     ANY(:ids) AND is_verified_purchase IS DISTINCT FROM (product_id = ANY(:true_ids))`.
     It does not touch `updated_at` (that is the author's edit time) or the aggregates
     (the badge is not an aggregate input).
- **Why `R_user` is needed (the create race).** Under READ COMMITTED, take a review
  INSERT and a payment hook that run concurrently, without a shared lock:
  - the create reads evidence before the payment commits, so it computes `false`;
  - the hook's step 2 does not see the uncommitted review, so it updates nothing;
  - the badge is then stale forever.

  With `R_user`, whichever runs second waits for the first to commit. It then reads with a
  fresh statement snapshot and sees the other's write. The same argument covers two orders
  of one user changing concurrently (one granting, one revoking). Test C1/C2, §6.3.

### 3.3 Review use cases (`app.engagement.application.services.reviews`)

Ports (in `engagement/application/ports.py`):

```python
class ReviewStore(Protocol):
    async def lock_user(self, user_id: UUID) -> None                        # R_user
    async def live_for(self, user_id: UUID, product_id: UUID) -> Review | None
    async def get_own_for_update(self, review_id: UUID, user_id: UUID) -> Review | None
    async def insert(self, new: NewReview) -> Review                        # IntegrityError -> ReviewAlreadyExistsError
    async def update(self, review_id: UUID, *, rating: int, body: str | None,
                     verified: bool, at: datetime) -> Review
    async def soft_delete(self, review_id: UUID, *, at: datetime) -> None
    async def visible_totals(self, product_id: UUID) -> tuple[int, int]     # (sum, count)
class ReviewableProducts(Protocol):                                         # Catalog adapter
    async def lock(self, product_id: UUID) -> ReviewableProduct | None      # FOR NO KEY UPDATE
    async def set_rating(self, product_id: UUID, average: Decimal, count: int) -> None
PurchaseEvidence = Callable[[UUID, Sequence[UUID]], Awaitable[set[UUID]]]  # ordering.public
```

- **`create_review(store, products, evidence, *, user_id, product_id, rating, body, now)`**
  1. Validate rating, `normalise_body`, `content_refusal`. Each refusal raises before any
     lock.
  2. `store.lock_user(user_id)` (`R_user`).
  3. `products.lock(product_id)`. Missing, deleted or invisible → `ProductNotFound` (404).
  4. `store.live_for(...)`. If one exists → `ReviewAlreadyExistsError` (409).
  5. `verified = product_id in await evidence(user_id, [product_id])`.
  6. `store.insert(...)`.
  7. `_recompute(store, products, product_id)`.
- **`edit_review(…, review_id, rating?, body?)`**
  1. Validate.
  2. `lock_user`.
  3. Unlocked read of `product_id` from the row. `product_id` is immutable, so it is safe
     to lock by it.
  4. `products.lock(product_id)`. There is no visibility check: an edit of a review on a
     product hidden later still works.
  5. `get_own_for_update`. Missing, someone else's or deleted → 404.
  6. Recompute `verified` from evidence, then `store.update`.
  7. `_recompute` only if `rating` changed.
- **`delete_review(…, review_id)`:** `lock_user`, then the product lock, then
  `get_own_for_update` (404 rules as above), then `soft_delete`, then `_recompute`.
- **`_recompute(store, products, product_id)`:** `(s, n) = visible_totals(product_id)`,
  then `products.set_rating(product_id, rating_average(s, n), n)`.
- **`recompute_product_rating(session, product_id)`** (published, §3.6): the caller must
  already hold the product lock. VS-037 calls it after toggling `is_hidden` / `hidden_at`.

### 3.4 Catalog additions (`app.catalog.public`)

```python
@dataclass(frozen=True) class ReviewableProduct: id: UUID; visible: bool; live: bool; purchase_mode: PurchaseMode | None
async def lock_product_for_reviews(session, product_id) -> ReviewableProduct | None
    """`FOR NO KEY UPDATE`: serialises review aggregate writers; never blocks FK key-share locks."""
async def set_review_aggregates(session, product_id, average: Decimal, count: int) -> None
    """Absolute values under that lock; bumps neither `version` nor `updated_at` (ADR-020 d5)."""
async def visible_product_id(session, slug: str) -> UUID | None
```

- `FOR NO KEY UPDATE` rather than `FOR UPDATE`, for two reasons:
  - The `reviews.product_id` FK check takes `FOR KEY SHARE`, which a `FOR UPDATE` would
    block.
  - It matches the lock a plain `UPDATE` takes, which is what `adjust_wishlist_count`
    takes (`catalog/public.py:41-45`).
- Admin edits' `get_for_update` (`product_repository.py:121-130`, `FOR UPDATE`) still
  serialises with it, harmlessly.
- `ck_products_rating_range` (`models.py:254`) and `ck_products_review_count_non_negative`
  (`:256`) remain the backstop.

### 3.5 Routes (`app.engagement.api.reviews`, `app.engagement.api.review_schemas`)

- The public list is under the products router prefix
  (`/products/{slug}/reviews`, mounted from Engagement). `/me/reviews` and `/reviews` are
  mounted in `app/api/v1` beside wishlist.
- The write rate limit is a dependency built like `_wishlist_rate_limit`
  (`engagement/api/wishlist.py:94-108`): it depends on `current_verified_user`, so
  anonymous callers never spend the budget. `key_prefix="reviews"`, subject the user id.
- Cursor encode and decode copies the wishlist one (`wishlist.py:55-90`), keyed on
  `(created_at, id)`.
- Each write runs in the request's session and commits once.
  `ReviewAlreadyExistsError` → 409, `ReviewContentRejectedError` → 422 with `reason`,
  not found → `not_found_error()` (`identity/api/dependencies.py:196`).

### 3.6 Published interface (`app.engagement.public`; what VS-037, VS-043, VS-044, VS-045 consume)

```python
async def refresh_review_badges(session, *, user_id, product_ids, evidence) -> None   # §3.2; Ordering only
async def recompute_product_rating(session, product_id) -> None   # VS-037; caller holds the product lock
async def lock_review_for_moderation(session, review_id) -> ReviewRow | None   # VS-037; product lock first (§8.1)
async def set_review_hidden(session, review_id, *, hidden: bool, at) -> None   # VS-037; is_hidden + hidden_at together
async def reviews_for_export(session, user_id) -> list[ReviewRow]   # VS-044; all rows, deleted and hidden included
@dataclass(frozen=True) class ReviewRow: id; user_id; product_id; rating; body; is_verified_purchase;
    is_hidden; hidden_at; deleted_at; created_at; updated_at
```

- **VS-037:**
  1. Unlocked read of `product_id`.
  2. `catalog.public.lock_product_for_reviews`.
  3. `lock_review_for_moderation` (`FOR UPDATE`), then the state check (409 on a repeat).
  4. `set_review_hidden`.
  5. `recompute_product_rating`, then its audit row.

  `R_user` is not needed: hiding does not touch the badge.
- **VS-043:** `products.average_rating` / `review_count` are exact for visible reviews.
  Top-rated is a Catalog read and needs nothing from Engagement.
- **VS-044:** `reviews_for_export`. Each row says whether it is deleted (`deleted_at`) or
  hidden. Its `is_verified_purchase` is already masked by D14: the function reads each
  product's `purchase_mode` in one batched Catalog call. `ReviewRow` from the moderation
  helpers carries the stored value, for VS-037's admin view.
- **VS-045:** nothing to call. Reviews keep `user_id` and text. Because no author identity
  is ever exposed (D12), the author already displays as anonymous. If Q7 adds a display
  name, VS-045 must blank it.

---

## 4. Database

### 4.1 Is a migration needed?

Yes: one table and one `order_items` index (§4.1a). The aggregate columns, their CHECKs
and `ix_products_browse_rating` exist (`catalog/infrastructure/models.py:218-221`,
`:254-256`, `:290-294`).

### 4.1a The badge lookup, reasoned as an EXPLAIN from the existing indexes (no run)

`badge_product_ids(user_id, product_ids)` is written as two branches, each with its
predicate spelled out literally, so a partial index can match it:

```sql
SELECT product_id FROM order_items
 WHERE user_id = :u AND product_id = ANY(:p)
   AND product_type = 'stl' AND fulfillment_status IN ('awaiting_delivery', 'delivered')
UNION
SELECT product_id FROM order_items
 WHERE user_id = :u AND product_id = ANY(:p)
   AND product_type = 'physical' AND fulfillment_status IN ('delivered', 'picked_up')
```

**Every index on `order_items` today:**
- `ix_order_items_order_id (order_id)` (`ordering/infrastructure/models.py:394`, migration
  `03a4730dd046…py:252`)
- `ix_order_items_physical_status (fulfillment_status, order_id) WHERE product_type =
  'physical'` (`models.py:395-400`)
- `ix_order_items_stl_awaiting (created_at, id) WHERE stl AND awaiting_delivery`
  (`:401-407`)
- `uq_order_items_stl_ownership (user_id, product_id) WHERE product_type = 'stl' AND
  fulfillment_status IN ('pending','awaiting_delivery','delivered')` (`:409-417`)
- the PK, `uq_order_items_id_order (id, order_id)` (`c01e53ab3e0f…py:87`), and
  `uq_order_items_offer_once` (`d5507ee63176…py:19`, offer id)
- The FK `fk_order_items_order_owner (order_id, user_id)` creates no index.

**Expected plans:**
- **STL branch.** Its predicate (`stl` AND status in {awaiting_delivery, delivered})
  implies `uq_order_items_stl_ownership`'s (a subset of its status list), and the leading
  columns are `(user_id, product_id)`. So the plan is `Index Scan using
  uq_order_items_stl_ownership (user_id = :u AND product_id = ANY(:p))`, plus a status
  filter that drops `pending`. That is at most one row per product (the index is unique).
  **Served.**
- **Physical branch.** No index leads with `user_id`.
  - The only physical partial index leads with `fulfillment_status`. The planner could use
    `Bitmap Index Scan on ix_order_items_physical_status (fulfillment_status IN
    ('delivered','picked_up'))` and then filter `user_id` / `product_id` on the heap.
    That reads **every delivered or picked-up physical line of every customer**, which
    grows with all history.
  - The alternative is a `Seq Scan` on `order_items`.
  - Either way it is O(all received lines), not O(this user's lines). **Not served.**
- **The cost is not hypothetical.** The hook's step 2 limits the lookup to buyers with a
  live review, but `create_review` and `edit_review` always run it.

**Decision: PR A adds**

```sql
CREATE INDEX ix_order_items_badge_received ON order_items (user_id, product_id)
 WHERE product_type = 'physical' AND fulfillment_status IN ('delivered', 'picked_up');
```

- The physical branch then becomes `Index Scan using ix_order_items_badge_received
  (user_id = :u AND product_id = ANY(:p))`. That is O(this user's received lines of these
  products).
- The index holds only received physical lines, so it is small. Writes into or out of
  those two states maintain it (W4, W5, W6).
- A plain `CREATE INDEX` (not `CONCURRENTLY`) inside the migration transaction. It blocks
  `order_items` writes for the build, which is milliseconds at the current table size
  (local only; no production yet, final phase). The deploy note says so.
- CP2 still captures the real `EXPLAIN (ANALYZE, BUFFERS)` of both branches on seeded data
  to confirm.

### 4.2 Migration `<rev>_reviews_and_badge_index.py` (`down_revision = "595b7e6e2792"`)

```python
op.create_table(
    "reviews",
    sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
    sa.Column("user_id", sa.UUID(), nullable=False),
    sa.Column("product_id", sa.UUID(), nullable=False),
    sa.Column("rating", sa.SmallInteger(), nullable=False),
    sa.Column("body", sa.Text(), nullable=True),
    sa.Column(
        "is_verified_purchase", sa.Boolean(), server_default=sa.text("false"), nullable=False
    ),
    sa.Column("is_hidden", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    ),
    sa.PrimaryKeyConstraint("id"),
    # RESTRICT: reviews are history (entities "Deletion strategy"); only verified users write,
    # and the purge removes only unverified accounts, so it can never meet one.
    sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
    sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
    sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_reviews_rating_range"),
    sa.CheckConstraint(
        "body IS NULL OR (btrim(body) <> '' AND char_length(body) <= 2000)",
        name="ck_reviews_body_shape",
    ),
    sa.CheckConstraint("is_hidden = (hidden_at IS NOT NULL)", name="ck_reviews_hidden_shape"),
    sa.CheckConstraint("updated_at >= created_at", name="ck_reviews_updated_after_created"),
)
op.create_index(
    "uq_reviews_user_product_live",
    "reviews",
    ["user_id", "product_id"],
    unique=True,
    postgresql_where=sa.text("deleted_at IS NULL"),
)
# Public list and the aggregate: visible rows of one product, newest first.
op.create_index(
    "ix_reviews_product_visible",
    "reviews",
    ["product_id", sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
    postgresql_where=sa.text("deleted_at IS NULL AND NOT is_hidden"),
)
# GET /me/reviews.
op.create_index(
    "ix_reviews_user_live",
    "reviews",
    ["user_id", sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
    postgresql_where=sa.text("deleted_at IS NULL"),
)
# The badge evidence's physical branch (§4.1a); the STL branch uses uq_order_items_stl_ownership.
op.create_index(
    "ix_order_items_badge_received",
    "order_items",
    ["user_id", "product_id"],
    postgresql_where=sa.text(
        "product_type = 'physical' AND fulfillment_status IN ('delivered', 'picked_up')"
    ),
)
```

- `downgrade()` drops `ix_order_items_badge_received`, then the three `reviews` indexes,
  then the table.
- Reversible and backward compatible: a new table and a new index, and no existing code
  reads either. `OrderItemModel.__table_args__` gains the matching `Index(...)`
  declaration, so the parity test passes.
- `uq_reviews_user_product_live` also serves the hook's step 2 (`user_id`, `product_id`).
- VS-037's admin list (filters hidden/rating/product/user) is VS-037's to index if it needs
  to (`api-endpoints.md:632`).

### 4.3 Rows VS-036 writes

- `reviews`: insert, update and soft delete.
- `products`: `average_rating` and `review_count` only.
- No audit rows for customer review actions (wishlist precedent); VS-037 audits
  moderation.
- No outbox or notification rows.

---

## 5. Abuse and performance

- **Who may write.** Verified users only (BR-100, entities `:980`). Only the owner edits
  or deletes (`:987`), with 404 for anyone else.
- **Rate limit (Q6).**
  - Writes: 10 per hour per user, one bucket shared by POST, PATCH and DELETE (create /
    delete churn is one abuse shape). Constants `REVIEW_WRITE_LIMIT = 10` and
    `REVIEW_WRITE_WINDOW_SECONDS = 3600` in `engagement/domain/reviews.py`.
  - Public list: 600 per hour per IP (`PUBLIC_RATE_LIMIT`).
- **One per product.** D8 means a user can influence a product's average by at most one
  rating, with or without a purchase (SRS risk 9, `SRS.md:1577`).
- **Content.** D9. The filter is a guardrail, not a moderation system. Anything it misses
  is VS-037's hide.
- **Aggregate cost.** `SELECT COALESCE(SUM(rating),0), COUNT(*) FROM reviews WHERE
  product_id = :p AND deleted_at IS NULL AND NOT is_hidden` is an index-only range on
  `ix_reviews_product_visible`. That is O(reviews on that product), well under 1 ms at the
  expected scale (hundreds per product). SRS §12.2 rejects computing on read, not computing
  on write.
  - The product lock is held only for the review transaction (a few statements).
  - It serialises review writes, wishlist counter updates and admin edits **per product**,
    which is acceptable at this traffic.
- **Hook cost on money paths.**
  - One advisory lock per transaction.
  - One indexed `SELECT … FOR UPDATE` on `reviews`, which is empty in the common case.
  - Then return. The evidence query runs only when the buyer has a live review of a
    touched product.
- **No N+1.** The public list returns no per-row joins (no author). `/me/reviews` resolves
  product slugs in one `get_many` (wishlist pattern, `wishlist.py:133`).

---

## 6. Tests

`[M]` must pass before Done. `[N]` is nice to have. Lines, payments, refunds and chargebacks
are created through the real writers where cheap, otherwise seeded as VS-029/030 do. Every
guard's test must fail once the guard is removed.

### 6.1 Unit

- [M] `line_earns_badge`: every `OrderItemStatus` × `ProductType`. True only for STL
  `awaiting_delivery` / `delivered` and physical `delivered` / `picked_up`.
- [M] `content_refusal`: link positives (`http://x`, `HTTPS://X.COM`, `www.x`, `x.com`,
  `a@b.lb`, full-width dots after NFKC). Negatives (`5.0 stars`, `e.g.`, `3.5mm`). Profanity
  whole words, case- and NFKC-folded. A substring inside a clean word is not refused.
- [M] `normalise_body`: whitespace-only becomes None. 2000 accepted, 2001 rejected.
- [M] `rating_average`: (0,0) → 0.00, (5,1) → 5.00, (14,3) → 4.67, half-up at .005.
- [M] **Writers allow-list, layer 1** (extends `tests/unit/ordering/test_order_item_writers.py`).
  - `STATE_WRITERS = {set_line_status, set_line_delivered, move_line,
    cancel_order_lines}` must equal the `KNOWN_WRITERS` entries (`:13-22`) that assign
    `fulfillment_status`.
  - It is found by AST: an `update(<OrderItemModel alias>)` whose `.values(...)` names
    `fulfillment_status`, or a values dict with that key. The existing `_aliases` helper
    (`:32-50`) and `RAW_SQL` regex (`:10`) are reused.
  - `insert_lines` is the one listed exemption ("new rows are `pending`").
  - A new store method that writes the column and is not in `STATE_WRITERS` fails.
- [M] **Writers allow-list, layer 2: hook required.**
  - `KNOWN_LINE_STATUS_CALLERS` (`:24-29`, today four entries) is widened to every caller
    of a `STATE_WRITERS` method: exactly W1-W8, §3.2a.
  - For each caller, the AST asserts a call to `_refresh_review_badges` that comes after
    the store call in source order.
  - Fails on: a caller outside `ordering/public.py`, a caller not in the list, or a
    listed caller without the hook (or with it before the write).
  - The failure message names the function and points to §3.2a.
- [M] Architecture: `app.engagement.public` does not import `app.ordering`, and
  `python -c "import app.engagement.public, app.ordering.public"` succeeds in a fresh
  interpreter.
- [M] Use-case order with fakes:
  - `create_review` calls `lock_user` → `products.lock` → `live_for` → `evidence` →
    `insert` → `visible_totals` → `set_rating`.
  - Content refusal calls no port.
- [N] A property test: `content_refusal` never raises for any Unicode string up to 2000
  characters.

### 6.2 Integration (real Postgres)

API:
- [M] Non-buyer creates → 201, `is_verified_purchase=false`; aggregates 5.00/1.
- [M] Duplicate → 409 `REVIEW_ALREADY_EXISTS`; also while the first is hidden (set via SQL).
  After delete → 201.
- [M] Unverified user → 403; anonymous → 401; missing CSRF → 403.
- [M] Invisible, deleted or unknown product → 404 on create and on the public list.
- [M] Rating 0 or 6 → 422; a link body → 422 `link`; a profane body → 422 `profanity`.
- [M] Edit someone else's review → 404; edit a deleted one → 404; edit with no fields → 422.
- [M] Public list excludes hidden and deleted rows. The `rating` and `verified_purchase`
  filters work, and the cursor is stable under inserts.
- [M] `/me/reviews` shows the user's hidden review with `is_hidden=true`, and not their
  deleted one.
- [M] The 11th write in an hour → 429 with `Retry-After`; an anonymous POST spends no
  budget.

Badge (each through the real writer):
- [M] STL paid (webhook / `apply_result`) after the review exists → badge true. Then
  delivered → still true. Then a full refund → false.
- [M] Online physical paid → false. `shipped` → false. `delivered` → true. Pickup
  `picked_up` → true.
- [M] Cash: unpaid `shipped` → false. The handover → true. A partly refused cash order
  (one line cancelled `refused`, the rest handed over), where the review is for the refused
  line's product and that product has no other line → false
  (`docs/vertical-slice-plan.md:1063`, `:900`).
- [M] `shipped → returned` → false; `returned → shipped → delivered` → true.
- [M] Partial refund of a delivered line → still true. Full refund → false.
- [M] Fail that refund → still false. Settle it → still false. A void of a different,
  partial refund → unchanged. Each asserts `is_verified_purchase` and that `updated_at` is
  untouched.
- [M] A chargeback emptying a delivered line → false. One emptying an unfinished line
  (→ `cancelled`) → unchanged.
- [M] Two orders for the same product: refunding one while the other is delivered → stays
  true.
- [M] A review created **after** the purchase → true at creation (the evidence read).
- [M] WhatsApp-only product, reviewer with no line → false (BR-103).
- [M] **D14 (Q3).** A product with a delivered online line, switched to `whatsapp_only`:
  - the stored `is_verified_purchase` stays true;
  - the public list, `/me/reviews` and `reviews_for_export` show false;
  - `verified_purchase=true` returns an empty page.

  Switched back to `both`, the badge shows again, with no write to `reviews`.
- [M] A soft-deleted review is not updated by the hook. A hidden review **is** updated.
- [M] **B-LOSS: when the badge is lost, only the flag changes.**
  - **Setup:** P has three visible reviews, ratings 5, 4 and 2, so the average is 3.67
    and the count is 3. The 5-star one belongs to a buyer whose only earning line is
    `delivered`, so its badge is true. Snapshot `average_rating`, `review_count`,
    `products.version`, `products.updated_at`, and that review's `updated_at`.
  - **Act:** a full admin refund of that line (W6).
  - **Assert:**
    - the review's `is_verified_purchase` is false;
    - the review is still in the public list;
    - `average_rating` is 3.67 and `review_count` is 3;
    - `products.version`, `products.updated_at` and `reviews.updated_at` equal the
      snapshot;
    - no `products` UPDATE was issued (SQL capture on the session);
    - the public `verified_purchase=true` filter no longer returns it.
  - **Repeat:** the same assertions for a chargeback emptying the line.

Aggregates:
- [M] Create, edit rating, edit body only (no recompute, values unchanged), delete: after
  each, `average_rating` / `review_count` equal a fresh `AVG`/`COUNT` over visible rows.
- [M] `products.version` and `updated_at` are unchanged by every review write (ADR-020 d5).

Schema (PR A):
- [M] Each CHECK refuses its row by name: rating 0/6, blank body, 2001 characters,
  `is_hidden` without `hidden_at` and the reverse, `updated_at < created_at`.
- [M] The partial unique index: two live rows refused; a live plus a deleted row accepted.
- [M] FK RESTRICT on `users` and `products`.
- [M] Model–migration parity; upgrade → downgrade -1 → upgrade.

### 6.3 Concurrency (`tests/concurrency/test_review_races.py`, `meet_or_fail`)

- [M] **C1** Create racing an STL payment for the same user and product, both orders,
  50×: the final badge is true every time.
- [M] **C2** Two orders of one user, one handed over and one fully refunded concurrently,
  same product, 50×: the badge equals the evidence after both commit.
- [M] **C3** N=20 concurrent creates by different users on one product: `review_count`
  is 20 and the average is exact.
- [M] **C4** Concurrent edits of different reviews on one product, plus a delete: the
  aggregates match a fresh `AVG`/`COUNT`.
- [M] **C5** Two concurrent POSTs by one user for one product: one 201, one 409, never a
  500.
- [M] **C6** Review edit racing a wishlist add on the same product and an admin product
  edit: no deadlock, and `version` bumps only from the admin edit.
- [M] **C7** A refund (orders → lines → payments → refunds → `R_user` → reviews) racing a
  review edit by the same user (`R_user` → product → reviews): no deadlock (§8.1).
- [N] **C8** VS-031 cash refusal with a review on a refused line, racing a review create
  on another product by the same user: no deadlock (`R_user` before cart → phone).
- [M] **C9 Review create vs refund of the same line, both commit orders** (real Postgres,
  two connections, `meet_or_fail` barriers).
  - **Setup:** a user with one `delivered` physical line of product P (evidence true) and
    no review.
  - **Order A, refund first.** Tx R: claim → orders → lines → payments → refund INSERT →
    W6 (`refunded`) → hook takes `R_user`, then pauses at the barrier. Tx C: `POST
    /reviews` blocks on `R_user` (asserted via `pg_locks` / `pg_stat_activity`
    `wait_event_type = 'Advisory'`). Commit R, then C. **Expected:** C reads evidence
    after R's commit, so the review is created with `is_verified_purchase = false`.
  - **Order B, create first.** Tx C takes `R_user` → product → INSERT
    (`is_verified_purchase = true`), then pauses. Tx R runs to W6 and its hook blocks on
    `R_user`. Commit C, then R. **Expected:** R's hook finds the new review and reads its
    own `refunded` line, so it flips the badge to false.
  - **Both orders:** no deadlock or serialization error, both 2xx. The final badge equals
    a fresh evidence read (false). `review_count` is 1 and `average_rating` is the rating,
    unchanged by the flip.
  - 50 repeats per order.
- [M] **C10 Review create vs VS-031 cancellation, both commit orders.** The same harness,
  run as two variants:
  - **(a) Customer self-cancel** of an all-`pending` online physical order of P
    (`fulfillment/application/cancel_lines.py:59`): orders → lines → payments → refund
    INSERT → W2 hook (`R_user`), racing `POST /reviews` for P.
  - **(b) Admin cancel `refused`** of a cash `ready_for_pickup` line of P: W2 hook
    (`R_user`) → cart → phone (cash block), racing a review create for P.
  - **Both commit orders, each variant:**
    - no deadlock;
    - the review exists with `is_verified_purchase = false` (a cancelled line never
      earns);
    - the cancel's refund, the cash block in (b), and the order status are as without the
      race;
    - the aggregates are exact.
  - (b) also proves `R_user` sits before cart → phone, with no cycle against a checkout
    that holds the cart (`R_user` is never taken after the cart).
  - 50 repeats per order.

### 6.4 Security

- [M] The public payloads contain no `user_id`, email or user-identifying field (a schema
  scan).
- [M] Review ids of other users → 404 on PATCH and DELETE, with the same body as a missing
  id.
- [M] The client cannot set `is_verified_purchase`, `is_hidden` or `hidden_at` (extra fields
  are rejected or ignored, and the stored values are unchanged) (`api-endpoints.md:19`).

### 6.5 Smoke and e2e

- [M] e2e: register and verify → buy an STL through the mock → review → badge shown in
  the public list → admin full refund → badge gone → product aggregates still 1 review.
- [M] Smoke: the head is the new revision; the five routes are in OpenAPI.

### 6.6 Running

Sequential chunks, as in VS-030/031 (unit; integration engagement + catalog;
integration ordering + payments + fulfillment, because the hook touches them; concurrency;
e2e/smoke). Never the whole suite at once.

---

## 7. Docs and ADRs

- **ADR-044 "Reviews and the Verified Purchase badge"** records D3–D8, D11, D12, D14 and D15, and the index decision (§4.1a). It
  amends:
  - the VS-030 plan §3.7 hook list (writer-level, no fail/void/reissue hooks);
  - BR-102 / SRS §12.1 ("received" for physical lines, if Q2 is accepted);
  - database-design §12.1 (adds `hidden_at`, the CHECKs and the indexes).
- `docs/reviews.md` (new): the API, badge rules and the "which states earn it" table, aggregate
  rules, error codes, limits.
- `docs/requirments/database-design.md` §12.1, `entities-and-business-rules.md` Review,
  `api-endpoints.md` §14.1 (`REVIEW_CONTENT_REJECTED`, payload fields), and the glossary
  "Verified Purchase".
- `docs/frontend-handoff/openapi.json` (regenerated) and `BACKEND-RESPONSE.md:425`
  (aggregates are now live).
- `docs/vertical-slice-plan.md`: VS-036 status and an "As built" note. Also notes on
  VS-037 (use `lock_product_for_reviews`, then `lock_review_for_moderation`, then
  `recompute_product_rating`), VS-044 (`reviews_for_export`) and VS-045 (nothing to do
  unless Q7 adds a name).
- SRS edits (BR-102 wording, if Q2 is accepted) held for the owner's approval in PR B's docs
  commit.

---

## 8. Implementation steps, in order, with checkpoints

### PR A: schema only (branch `vs-036-schema`; merge first, under the migration lock)

1. Announce the migration lock (`CONTRIBUTING.md:42`). Re-derive the head
   (`595b7e6e2792` expected).
2. Add `ReviewModel` (declaration only) in `engagement/infrastructure/models.py`. Add the
   `Index("ix_order_items_badge_received", …)` declaration to `OrderItemModel.__table_args__`
   (`ordering/infrastructure/models.py:394-417`).
3. Hand-write the migration (§4.2). Check `alembic heads` = 1, then upgrade →
   downgrade -1 → upgrade.
4. Add the schema tests (§6.2 Schema), the parity entry and the reversibility block.
   Update database-design §12.1.
5. Run the unit and integration chunks, open PR A, and release the lock after the merge.

A reviewer check: `git diff --stat main…vs-036-schema -- src` lists only
`engagement/infrastructure/models.py` and `ordering/infrastructure/models.py`, with column,
constraint and index declarations only. A schema test asserts that the new index exists with
its exact predicate (`pg_indexes.indexdef`).

### PR B: code (branch `vs-036-reviews`, from `main` after PR A)

6. The pure rules (`engagement/domain/reviews.py`, `profanity.py`,
   `ordering/domain/badge.py`), with unit tests.
7. Catalog: `lock_product_for_reviews`, `set_review_aggregates`, `visible_product_id`.
8. Engagement: `SqlReviewStore`, the use cases, `refresh_review_badges`, and the §3.6
   interface.
9. Ordering: `SqlOrderStore.badge_product_ids`, `_refresh_review_badges` in the eight
   writers, and the writers AST test.
10. Routes, schemas, rate limit, error mapping, OpenAPI.
11. The concurrency suite (§6.3), security, e2e and smoke.
12. Docs and ADR-044.

### Checkpoints

| # | When | Reports |
|---|---|---|
| **CP1** | PR A merged | revision id; `alembic heads` (1); the up/down/up log; schema test counts; the `git diff --stat -- src`; "migration lock released" |
| **CP2** (owner sign-off) | after step 9 | the §3.1 badge table as tests (unit count); the writers AST test listing all eight writers; the captured SQL order of one refund transaction and one review create against §8.1; `EXPLAIN (ANALYZE, BUFFERS)` of both `badge_product_ids` branches (expected: §4.1a) and of `visible_totals`; the frozen §3.6 interface; chunk pass counts |

Steps 10–12 finish with full chunked runs, `ruff check`, `ruff format --check` and
`mypy src tests` clean. The plan status is then set to DONE.

### 8.1 Lock order per path, and why there is no cycle

Global rank (extends ADR-042 d8 and VS-030 plan D7, `VS-030…plan.md:128`):

`idempotency claim → orders → order_items (by id) → payments (by id) → refunds (by id) →
chargebacks → R_user (advisory, review) → products (FOR NO KEY UPDATE) → reviews (by id)`,
then the later advisory locks: the offer acquisition lock (ADR-037) and the payment-alert
lock (ADR-042 d19). VS-031's cart → phone lock comes last.

| Path | Locks, in order |
|---|---|
| Payment applied (STL) | orders → lines → payment → [`mark_order_paid` hook: `R_user` → reviews] → offer acquisition lock (`ordering_side.py:46-55`) |
| Cash handover | orders → lines → (cash payment INSERT) → [hook: `R_user` → reviews] |
| Physical transition | orders → lines → [hook: `R_user` → reviews] |
| Refund create | claim → orders → lines → payments → refund INSERT → [`refund_lines` hook: `R_user` → reviews] |
| Chargeback | claim → orders → lines → payments → refunds → chargeback → [hook: `R_user` → reviews] |
| VS-031 cancel (cash refusal) | orders → lines → payments → refund → [hooks: `R_user` → reviews] → cart → phone |
| Review create / edit / delete | `R_user` → products → reviews |
| VS-037 hide / restore | products → reviews |
| Wishlist add/remove | wishlist_items → products (UPDATE) |
| Admin product edit | products FOR UPDATE → reference rows FOR SHARE |
| Checkout | cart → … → INSERT orders / order_items (no hook: new lines are `pending`) |

**The proof (a rank argument).** Give each lock its rank in the line above:
- 1 claim, 2 orders, 3 lines, 4 payments, 5 refunds, 6 chargebacks;
- 7 `R_user`, 8 products, 9 reviews;
- 10 offer acquisition, 11 payment alert, 12 cart (VS-031 tail), 13 phone.

A deadlock needs a cycle in the waits-for graph, and so at least one transaction that holds a
lock of rank *j* while it waits for one of rank *i < j*. Every path is checked against that
below.

1. **Money paths (W1-W8 callers).** Ranks 2-3 come from `lock_order_for_change`
   (`ordering/public.py:192-198`) and 4-6 from the refund and chargeback services (ADR-042
   d8; `services/chargebacks.py:69`, `:72`, `:103`, `:110`, then lines at `:237`). The hook
   runs **inside** W1-W8, which always come after those locks:
   - refund create inserts the refund, then `refunds.py:274`;
   - chargeback inserts at `:110`, then `chargeback_lines` at `:237`;
   - VS-031 runs `cancellation_refund` at `cancel_lines.py:117`, then `cancel` at `:126`.

   The hook then takes 7, then 9, and **never 8**: the badge is not an aggregate input
   (D15). After the hook, a money path takes only 10 (`ordering_side.py:48`), 11
   (alerts, last, ADR-042 d19) or 12 → 13 (`cancel_lines.py:142`). All are higher ranks.
   So a money path only ever waits upward.
2. **Review create, edit and delete.** These take 7, 8 and 9, in that order (§3.3). They
   never take ranks 1-6 (the evidence read is a plain `SELECT` with no lock) and never
   10-13. They only ever wait upward.
3. **VS-037 hide and restore.** These take 8 → 9. The `product_id` is read unlocked first;
   it is immutable. Upward only.
4. **Wishlist.** Its own `wishlist_items` row (outside this chain, and never held by any
   path above), then products (8) through the `UPDATE`. It holds nothing ranked above 8.
5. **Admin product edit.** Products `FOR UPDATE` (8), then reference rows `FOR SHARE`,
   which no path above takes. It holds 8 and never waits on 7 or 9.
6. **Checkout.** Cart (12) → inserts. It takes no rank 2-9 lock on an *existing* row: new
   `orders` and `order_items` rows are invisible, and W-writers are never called. Its cart
   lock and VS-031's rank-12 cart lock are the same resource, but checkout holds nothing
   VS-031 waits for in ranks 2-11. VS-031 reaches the cart only after its own 2-7 locks,
   which checkout never takes, so no cycle passes through the cart.

Since every transaction acquires in non-decreasing rank, the graph is acyclic. Two waits
at the same rank are resolved separately:
- Rank 7 is one key per transaction, and re-entrant.
- Rank 9 is taken `ORDER BY id` in the hook. Review paths lock one row.
- Ranks 2-6 keep their existing ordering (by id).

C7, C9 and C10 (§6.3) are the runtime check; CP2 captures the SQL order of a refund and of
a review create.

- **No cycle.** Every path acquires in rank order. Review paths never take an order-chain
  lock, the cart or the phone lock. Money paths never take `products`.
  - `R_user` → reviews in the hook, and `R_user` → products → reviews in review paths,
    agree.
  - VS-037 skips `R_user` but keeps products before reviews.
  - Wishlist holds only its own row before `products`, and never takes `R_user` or
    reviews.
  - The offer-acquisition lock is taken after `R_user` on the payment path. No path takes
    it before `R_user` (`submit_offer` writes no line state).
- **Per-user, not per-(user, product).** One key per transaction (an order has one
  customer), and the lock is re-entrant. Two hook batches in one transaction can therefore
  never interleave two keys in different orders.
- **`hashtext` collisions** between users only serialise unrelated work briefly.

---

## 9. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | A future line-state writer forgets the hook, and the badge goes stale | AST test (§6.1) fails on a new caller of a state writer without `_refresh_review_badges` |
| R2 | D4 is narrower than BR-149 read literally (a paid online physical line earns nothing until delivered) | Q2; the change is one constant (`BADGE_STATES`) |
| R3 | Import cycle Engagement ↔ Ordering | `engagement/public.py` takes `evidence` as a callable; architecture test (§6.1) |
| R4 | `badge_product_ids` seq-scans `order_items` | **Closed (Revision 1):** the STL branch uses `uq_order_items_stl_ownership`; the physical branch gets `ix_order_items_badge_received` in PR A (§4.1a); CP2 confirms with `EXPLAIN (ANALYZE)` |
| R5 | Product-row contention between reviews, wishlist and admin edits | Locks are short (single-statement work); C6 proves no deadlock |
| R6 | The profanity list over-blocks or under-blocks (Arabic and Arabizi) | Whole-word matching only; the list is a reviewed constant; VS-037 hide covers misses (Q5) |
| R7 | Existing badges at deploy | None exist (new table); no backfill needed |
| R8 | A read path forgets the D14 mask and shows a badge on a WhatsApp-only product | Every read goes through `badge_shown`; D14 tests cover the public list, its filter, `/me/reviews` and the export |

---

## 10. Owner questions (each with a recommendation)

**All answered (owner, 2026-10-25).**
- Q1, Q2 and Q4-Q10: **DECIDED as recommended.**
- Q3: **DECIDED differently**: never show the badge on WhatsApp-only products, and keep the
  purchase data (D14).

The questions are kept below as they were asked.

1. **Moderation columns: `is_hidden` plus `hidden_at` with a tie CHECK (D3)?**
   database-design `:1642` has `is_hidden`; entities `:956`, `:971` has `hidden_at`.
   *Recommendation:* yes, both. The boolean serves the partial index, and the timestamp
   keeps "when". The CHECK makes them one fact. Who hid it and why go to VS-037's audit
   row.
2. **Physical lines earn the badge at `delivered` / `picked_up` only (D4), not at
   payment?** The slice text says "paid (BR-149), non-refunded line" (`:1056`).
   *Recommendation:* yes. A review is backed by an item received. It needs no Payments
   read, and a cash order already works this way. Amend BR-102 and SRS §12.1 wording in
   ADR-044. If you choose BR-149 literally instead, `BADGE_STATES` gains `in_production`,
   `ready_to_ship`, `shipped` and `ready_for_pickup` for online lines, the evidence query
   must also check the payment, and cancel and chargeback-cancel become revoking hooks.
3. **A product switched to WhatsApp-only after online sales: badge from the records, or
   never?** BR-103 (`SRS.md:290`) gives "no purchase record" as the reason.
   *Recommendation:* follow the records: a real platform purchase stays verified. A
   product that was always WhatsApp-only has no lines, so it never badges.
   **DECIDED (owner, 2026-10-25):** never show the badge on a WhatsApp-only product, and
   keep the purchase data. D14: the stored flag follows the evidence, and every read masks
   it.
4. **May the author edit a hidden review, and does it stay hidden?**
   *Recommendation:* yes, it may be edited, and it stays hidden. Only an administrator
   restores (VS-037). Deleting it is also allowed.
5. **Profanity list: a code constant (English plus Arabic and Arabizi), whole-word
   matching, refusal 422 `REVIEW_CONTENT_REJECTED`?**
   *Recommendation:* yes. The owner supplies or approves the word list in PR B. It is not
   an operator setting in V1.
6. **Limits: 10 review writes per user per hour, and the public list at 600 per hour per
   IP, as code constants?**
   *Recommendation:* yes (VS-023/024 precedent, `wishlist.py:36` 120/h, offers 20). Promote
   one to a setting only if an operator needs to tune it.
7. **Public author label.** There is no name column, and an email is never shown.
   *Recommendation:* show none in V1 (the frontend renders "Customer" or "Verified buyer").
   A display name is a later identity change, and VS-045 would blank it.
8. **Body length 2000 and an optional body (rating-only reviews allowed)?**
   *Recommendation:* yes. `ReviewCreate.body` is optional (`api-endpoints.md:998`).
9. **No audit rows for customer review writes?**
   *Recommendation:* yes (wishlist precedent). VS-037 audits moderation, and the
   `reviews` rows themselves keep `created_at` / `updated_at` / `deleted_at`.
10. **May ADR-044 amend the VS-030 plan's hook list** (`:171`, `:698`) to the writer-level
    hook, with no fail/void/reissue hooks?
    *Recommendation:* yes. Those operations never change a line state (ADR-042 d1, d23;
    `refunds.md:26`, `:30`, `:65`), and tests (§6.2) prove the badge unchanged across them.
