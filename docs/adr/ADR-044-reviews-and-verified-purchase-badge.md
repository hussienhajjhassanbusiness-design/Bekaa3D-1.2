# ADR-044: Reviews and the Verified Purchase badge - the badge is a projection of current line facts, recomputed in Ordering's line writers; ratings are exact aggregates under the product lock (VS-036)

**Status:** Amended 2026-11-06, see [Amendment](#amendment-2026-11-06-links-no-op-edits-hidden-products-chargebacks); amended 2026-11-05, see [Amendment](#amendment-2026-11-05-a-deleted-customers-reviews). Accepted (2026-10-27, VS-036 PR B). Proposed 2026-10-25 with PR A (schema); PR B built the behaviour and recorded decisions 11-20 below. VS-037 (2026-10-27) recorded decisions 21-27, the moderation path.
**Date:** 2026-10-25
**Source basis:** [VS-036 slice](../vertical-slice-plan.md#vs-036--reviews-and-verified-purchase-badge); [plan](../plans/VS-036-reviews-plan.md) (Revision 1, owner answers Q1-Q10 of 2026-10-25); SRS §3.8 BR-100 to BR-105, BR-149, §12.1, §12.2, INV-17; database-design §12.1; [ADR-019](ADR-019-manual-stl-delivery.md) d5; [ADR-020](ADR-020-optimistic-versioning-for-admin-edits.md) d5; [ADR-042](ADR-042-refunds-voids-and-chargebacks.md); [ADR-043](ADR-043-cancellation-and-returns.md); [VS-037 plan](../plans/VS-037-review-moderation-plan.md) (owner answers Q1-Q7 of 2026-10-27).
**Amends:**
- database-design §12.1: adds `hidden_at`, the named CHECKs and the indexes.
- The [VS-030 plan](../plans/VS-030-refunds-settlement-plan.md) §3.7 hook list: the hook moves to the line writers, and fail/void/reissue get no hook.
- SRS BR-102 to BR-104, §12.1 and INV-17 wording: physical lines count once received (Q2); WhatsApp-only products never show the badge (Q3). Applied in PR B's docs commit.

**Applies first to:** migration `eeed201dcfd2` (`reviews`, `ix_order_items_badge_received`).

## Context

Any verified user may review any product (BR-100), once per product (BR-101). A
Verified Purchase badge must honestly reflect current purchase evidence: it is granted when
a purchase is paid and removed when it is refunded (BR-102 to BR-104, INV-17). The documents
disagreed on the moderation state: database-design §12.1 has `is_hidden`, while the entities
document has `hidden_at`. The VS-030 plan named refund use cases as hook points, but fail, void
and reissue never change a line.

## Decision

1. **Moderation is both `is_hidden` and `hidden_at`** (Q1), tied by `ck_reviews_hidden_shape`
   (`is_hidden = (hidden_at IS NOT NULL)`). VS-036 never writes them; VS-037 does. Who hid a
   review, and why, goes to VS-037's audit row.
2. **One live review per user and product:** `uq_reviews_user_product_live` (partial, `deleted_at IS NULL`).
   A hidden review is live and blocks a second one. A deleted one frees the pair. The API
   answers 409 `REVIEW_ALREADY_EXISTS`.
3. **The badge is recomputed from current line facts, never toggled** (Q2). It is earned by an
   STL line in `awaiting_delivery` / `delivered` (ownership, ADR-019 d5) or a physical line in
   `delivered` / `picked_up`. These states are reachable only after payment, or at the cash
   handover, so line status alone is the evidence and Payments is never read. A partial refund
   keeps the badge. A failed or voided refund changes nothing, because neither reopens or moves
   a line (ADR-042 d1, d23).
4. **The recompute runs in Ordering's eight line-status writers**, after the write and in the
   caller's transaction (plan §3.2a). A static test fails if a new writer lacks it.
5. **One per-user advisory lock** serialises badge writers with review creation. It is taken
   after the order-chain locks (orders, lines, payments, refunds, chargebacks) and before the
   product lock and the VS-031 cart/phone locks. Review paths never take an order-chain lock.
6. **Ratings are exact aggregates** (`SUM` / `COUNT` over visible reviews), written under the
   product row lock (`FOR NO KEY UPDATE`) in the review's transaction. They bump neither
   `products.version` (ADR-020 d5) nor `updated_at`. Losing a badge never touches them.
7. **A WhatsApp-only product never shows the badge** (Q3, owner). The stored value keeps
   following the purchase data, and every read masks it.
8. **`ix_order_items_badge_received`** serves the physical branch of the evidence query. No
   existing index led with `user_id` for physical lines. The STL branch uses
   `uq_order_items_stl_ownership`.
9. **`reviews.user_id` is RESTRICT.** Reviews are history, and the unverified-account purge never
   reaches a verified author.
10. **No author identity is exposed** (Q7). There is no name column, and an email is never shown.
    Limits are code constants (Q6): 10 writes per user per hour, and the public list at 600
    per hour per IP. The profanity list is a reviewed code constant (Q5). Customer review
    writes are not audited (Q9).

### Decisions recorded in PR B

11. **Hook mechanics.** `_refresh_review_badges` in `ordering/public.py` runs in W1-W8 after the
    status write and its history rows. It calls `engagement.public.refresh_review_badges`, which
    takes `R_user`, locks the user's live reviews of the touched products `FOR UPDATE` by id, and
    only then (if any exist) reads evidence and updates `is_verified_purchase` where it differs.
    `updated_at` and the aggregates are never touched (D15). The `R_user` and reviews statements
    are sent on every hooked write; a row is locked only when a review exists.
12. **Uniform hook, no no-op guard** (owner, CP2). W2, W3, W7 and W8 cannot change a badge but
    call the hook anyway, so one static rule covers every writer. Six lock-order tests now
    expect `R_user` (rank 7) and `reviews` (rank 9) after payments on W1 and W8 paths.
13. **Evidence query.** `SqlOrderStore.badge_product_ids` is a two-branch `UNION` with the
    product type and statuses inlined as literals, so a generic plan still matches
    `uq_order_items_stl_ownership` and `ix_order_items_badge_received`. Ordering publishes it
    as `purchase_evidence(session)`; `engagement.public` never imports Ordering.
14. **Visible-row predicate.** Reads filter `NOT is_hidden` (bare), never `is_hidden IS FALSE`,
    which the planner does not match to `ix_reviews_product_visible` (found at CP2).
15. **Timestamps.** Edit and soft delete stamp `clock_timestamp()`, which can never precede
    `created_at` (`ck_reviews_updated_after_created`), unlike the transaction's `now()`.
16. **Duplicates.** The create pre-checks under `R_user`; the INSERT uses `ON CONFLICT DO NOTHING`
    on the live unique index as the backstop, so a race is a 409, never a 500.
17. **Aggregates on every edit.** An edit recomputes in full even if only the body changed
    (owner instruction); the values are unchanged in that case.
18. **Public list.** `GET /products/{slug}/reviews` (not `{id}`), with the storefront's 404 rule.
    On a WhatsApp-only product, `verified_purchase=true` returns an empty page and `false`
    returns every row. Limits: 600/h per IP for the list, 10/h per user shared by POST, PATCH
    and DELETE (`engagement/domain/review_limits.py`).
19. **R_user is load-bearing, proven.** Race C11 stalls a create after its evidence read (a held
    `users` row blocks its FK check) while a refund of the same line runs. With `R_user` the
    refund's hook waits and the badge ends false; with `R_user` removed the test fails with the
    badge left true on a refunded line.
20. **Profanity list needs owner review before go-live.** `engagement/domain/profanity.py` is a
    first draft (English, Arabic, Arabizi) matched as whole words after NFKC and casefold.

### Decisions recorded in VS-037 (review moderation)

21. **Lock order: the product (`FOR NO KEY UPDATE`), then the review row (`FOR UPDATE`), no
    `R_user`.** Hiding never touches the badge. The `product_id` is read unlocked first (it is
    immutable). Ranks 8 → 9 only, so no cycle with create/edit/delete (7 → 8 → 9) or the badge
    hook (7 → 9, never 8). Races M1-M6 run both commit orders; locking the row first deadlocks
    M1.
22. **A soft-deleted review is missing for moderation** (Q1). List, detail, hide and restore
    answer the same 404 as an unknown id. `lock_review_for_moderation` returns deleted rows, so
    `moderate_review` re-checks `deleted_at` after the row lock.
23. **Repeat actions are 409 `INVALID_STATE_TRANSITION`** (Q7), with `is_hidden` in the body. The
    check reads the locked row, never an earlier read. Nothing is written and nothing audited.
24. **The reason is optional and audit-only** (Q2): trimmed, at most 500 characters, no control
    characters. There is no column, no author notification and no appeal in V1.
25. **Audit rows** `review.hidden` / `review.restored` (`entity_type = "review"`). `before_data`
    and `after_data` hold `is_hidden`, `hidden_at`, `product_id` and (after) `reason`; never the
    body, the author's id or email. They are written in the same transaction as the toggle and the
    exact recompute (d7). List and detail reads are not audited (Q4: no PII shown).
26. **No admin `created_at` index** (Q3). At 100,000 live reviews the unfiltered admin page is a
    parallel seq scan plus a top-N heapsort: about 13 ms p95 in SQL and 36 ms p95 over HTTP,
    below the 50 ms trigger. The user filter uses `ix_reviews_user_live`, and product plus
    `hidden=false` uses `ix_reviews_product_visible`. No migration; the head stays
    `eeed201dcfd2`.
27. **The admin view shows the badge twice** (Q6): `is_verified_purchase` is the stored evidence,
    and `badge_shown` is the D14 mask the storefront applies. `verified_purchase` filters the
    stored flag. No author identity beyond `user_id`.

## Consequences

- PR A adds the table, its four CHECKs, two FKs, three indexes and the order_items index. No
  application code reads or writes them until PR B.
- VS-037 reuses the exact recompute (inside Engagement, through its `ReviewModerationStore` port; the
  `engagement.public` helpers are unchanged). VS-044 reads `reviews_for_export`, which applies the
  mask. VS-045 has nothing to blank while no author identity is shown.
- Accepted with PR B (decisions 11-20). Any later change to the badge states is one constant,
  `ordering/domain/badge.py:BADGE_STATES`, plus its tests.

## Amendment (2026-11-05): a deleted customer's reviews

A deleted customer's reviews stay public and anonymous (owner decision, after the end-to-end rehearsal raised it; ADR-047 did not say). Account deletion leaves the rating, the text and the Verified Purchase badge, so product ratings and their aggregates do not move. Anonymous here means no public or customer-facing read names an author: `PublicReviewRead` has no author field, and `reviews.user_id` stays for the administrator's review queue, where it now leads to an anonymised account. The customer can delete a review before closing the account if they want its text gone; deletion does not do that for them. `test_a_deleted_customers_review_stays_public_and_anonymous` holds this.

## Amendment (2026-11-06): links, no-op edits, hidden products, chargebacks

Owner decisions on the open VS-036 audit items ([audit](../audits/VS-036-audit.md) A-08, A-09, Q-1 to Q-3).

1. **Any real domain ending is a link** (Q-1). The closed list of 15 endings let `cheap3d.shop` or `prints.store` through. A word followed by a dot and a label is now a link when the label is one of IANA's root-zone TLDs. That covers 1,436 ASCII endings plus each internationalised one in Unicode (`موقع.شبكة`), from `engagement/domain/iana_tlds.txt`, a verbatim copy of `https://data.iana.org/TLD/tlds-alpha-by-domain.txt` (version `2026110500`). Refresh it by replacing that file; nothing else changes. Schemes, `www.` and e-mail addresses are refused as before.
   - **Matching:** a label is the run of letters, marks and digits after a dot that follows one, so Indic endings such as `भारत` are reached (a regex word character has no combining marks). Only an `xn--` label holds a hyphen, so `foo.com-it` reads as `com`. `test_every_listed_ending_is_reached_by_the_matcher` checks every ending.
   - **Accepted cost:** many endings are ordinary words (`it`, `so`, `me`, `love`, `today`) or file extensions (`zip`, `md`, `py`, `app`, `dev`, `mov`), so a missing space after a full stop, or a file name, can read as a domain. `Great print.It works` and `The STL came as model.zip` are refused with `reason: link`; the customer adds the space or leaves the extension out. Text written normally is not affected (`5.0 stars`, `e.g.`, `3.5mm`, `v1.2`, `Mr. Smith`). `test_a_missing_space_after_a_full_stop_can_read_as_a_domain` holds this.
2. **An edit that changes nothing writes nothing** (A-09; amends decision 17). When the rating and the trimmed text both equal the stored ones, the PATCH answers `200` with the review as stored: `edited` stays as it was, `updated_at` does not move, and nothing is recomputed. Any real change still recomputes in full.
3. **An author may edit or delete a review after its product is hidden or archived** (Q-2). Create still needs a live, visible product (FR-14 "Given the product is visible"). An edit is the author's own text about a purchase that happened, so `_lock_own` does not check visibility, and the aggregates are recomputed as on any edit. `test_the_author_may_edit_and_delete_a_review_after_its_product_is_hidden` holds both cases, for a hidden and an archived product.
4. **A chargeback counts like a refund for the badge** (Q-3). BR-149's "a line cancelled by a chargeback is still a paid line" is about money and history, not the badge. The badge follows `BADGE_STATES`: a chargeback that leaves a received line `delivered` or `picked_up` keeps it, as a partial refund does, and one that empties the line makes it `refunded` and removes the badge, as a full refund does. A chargeback only cancels unfinished physical lines, which never had the badge. `test_a_chargeback_counts_like_a_refund_partial_keeps_and_emptying_revokes` and `test_a_chargeback_emptying_a_delivered_line_revokes_and_an_unfinished_one_does_not` hold this.
5. **The CSRF check comes before the write limit** (A-08). On review, cart, wishlist and offer writes, `require_csrf` runs before the per-user limit, so a cross-site request without the header is `403 CSRF_INVALID` and spends none of the customer's budget. The administrator's `POST /api/v1/auth/mfa/recovery-codes/regenerate` follows the same order, because its per-IP limit guards a password check. `tests/integration/test_csrf_before_rate_limit.py` covers all thirteen routes. No other route runs a limit before `require_csrf`.
