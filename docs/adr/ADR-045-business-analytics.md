# ADR-045: Business analytics - per-line revenue from one read-only snapshot, a chargeback counted once, Beirut days, a reporting context that joins no other context (VS-043)

**Status:** Accepted (2026-10-27, VS-043).
**Date:** 2026-10-27
**Source basis:** [VS-043 slice](../vertical-slice-plan.md#vs-043--business-analytics); [plan](../plans/VS-043-business-analytics-plan.md) (owner answers Q1-Q12 of 2026-10-27, all as recommended); SRS §15.5, F-120 to F-127, BR-149, BR-126; FR-18; [ADR-024](ADR-024-cash-on-delivery-and-courier-priced-shipping.md) d1, d11 and its VS-043 open item; [ADR-042](ADR-042-refunds-voids-and-chargebacks.md) d2-d4, d14, d16-d19; [VS-030 plan](../plans/VS-030-refunds-settlement-plan.md) §3.7.
**Amends:**
- ADR-024's open item for VS-043 (a line cancelled after a chargeback counted twice): resolved by decision 2.
- SRS §15.5 and BR-149: the dating and the chargeback-cancelled line, applied in the VS-043 docs commit.
- api-endpoints §27 (route rows), new §27.1 (metric definitions), §5.2 (`INVALID_DATE_RANGE`) and §30 (response schemas).

**Applies first to:** no migration; the alembic head stays `eeed201dcfd2` (decision 8).

## Context

The administrator needs revenue split by physical and STL, attributed per line, plus recent
purchases, customer statistics, pending offers, top-rated products and best-selling STLs
(F-120 to F-126). Revenue is "paid line amounts minus refunds" (SRS §15.5), but the money paths
of VS-030 and VS-031 gave that phrase three traps: failed, voided and late-capture refunds; a
chargeback that cancels an unfinished line (ADR-042 d17), which a naive reading would both
exclude and subtract; and the date a refund belongs to. The figures read Ordering, Payments,
Catalog, Identity and Negotiation, which ADR-005 forbids joining directly. FR-18 also requires
that analytics never disturb operational transactions and never show fabricated zeros.

## Decision

1. **The metric definitions are api-endpoints §27.1**, written before the code. Revenue of a
   paid line = its order-time `line_total_cents` minus its items in `admin` and `cancellation`
   refunds that are `pending` or `settled`, minus its chargeback items. A failed refund counts
   only through its reissue; voided and `late_capture` refunds never count; there is no
   shipping and tax is 0 (ADR-024 d1). A chargeback's `excess_cents` is never put on a line; it
   is reported apart as `unattributed_chargeback_excess_cents` and not subtracted.
2. **A chargeback is counted once: the exclusion side drops.** A `cancelled` line of a paid
   order is excluded only when nothing counts against it: no item in a pending, settled or
   failed-not-reissued refund (not `late_capture`) and no chargeback item. That is L2's "bare
   cancel" (`payments/domain/refunds.py`, `line_balances`). A line a chargeback cancelled carries
   the chargeback's items, so it stays a paid line and nets to 0; excluded lines and subtracted
   items are disjoint by construction. A cash line refused before the handover has nothing
   against it and is not a paid line (BR-149). Proven by R9, R9b and R10 and by the mutation
   `is_paid_line = not cancelled`, which those tests catch.
3. **Each line belongs to its payment's Beirut day.** The payment is the order's one payment
   that reached paid (`uq_payments_one_live`), dated by `verified_at`; for cash that is the
   handover (`insert_cash_payment`). Refunds and chargebacks count against that day, so a past
   period changes when a later refund lands (Q2). Days are `Asia/Beirut` calendar days through
   `zoneinfo`, with `tzdata` a runtime dependency: in 2026 the spring day 03-29 lasts 23 hours
   and the autumn day 10-24 (the Saturday) 25 hours.
4. **A `reporting` context reads every other context through a port** (Q4). Each context
   publishes unlocked, read-only reporting functions in its `public.py`; Payments' SQL joins only
   Payments' tables, and the reports combine the rows in memory. VS-030 plan §3.7's
   `refunded_cents_by_line` and `unsettled_refund_exists` are built here, with
   `refund_covered_lines` for decision 2. The context is in the architecture test's `CONTEXTS`.
5. **One read-only snapshot per request.** `report_session` opens its own connection and starts
   with `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY` and
   `SET LOCAL statement_timeout = 5000`. Every port reads one snapshot, nothing can write (a
   write fails with "read-only transaction", proven over HTTP), and a report never shares a
   transaction with an operational write.
6. **A failure is an error, never zeros.** No report catches an exception. A database failure is
   503 `SERVICE_UNAVAILABLE` through the existing handler; a statement timeout (SQLSTATE 57014)
   is mapped to the same 503 in `report_session`; anything else is 500. Failure injection on
   every port of every route proves it.
7. **Ranges and access.** `from` and `to` are inclusive Beirut dates, default the last 30 days,
   at most 366, years 2020-2100; a range error is `400 INVALID_DATE_RANGE` naming the field
   (Q6). The routes are GET only behind the admin boundary (MFA), with a 30 per minute
   per-administrator analytics limit on top of the router's 300 (Q8). Reads are not audited and
   no body carries an email, name, phone, address or provider reference (Q7).
8. **No index without a measurement** (Q5). At 100,000 payments (90,000 paid) the 30-day window
   is 11.8 ms p95 and the recent-purchases page 30.3 ms p95, both sequential scans under the
   50 ms trigger, so `ix_payments_reached_paid_verified` is not added. The chunked reads bind one
   `uuid[]` per chunk (`= ANY`): with one bind per id the 366-day report took 16.4 s; with the
   array it takes 2.06 s p50 / 2.37 s p95, just over the plan's 2 s budget (see Consequences).

## Consequences

+ Revenue, balances and the badge read the same "paid line" rule, so the reports cannot
  disagree with refunds about which line was paid.
+ A broken database or a slow query shows the administrator an error, never a quiet zero, and
  a report can never block or write to an operational row.
+ No schema change; the published refund reads VS-045 needs already exist.
- Past periods restate when a refund lands; ranges compare cohorts by payment day, not cash
  movements by day.
- A 366-day report at 100k payments takes about 2.4 s p95 in process, loading every paid line
  of the range into memory. Above the plan's 2 s budget; acceptable at the shop's current scale,
  revisited by the trigger below.
- Each analytics request holds a second pooled connection for its duration (bounded by the
  30/min limit and the 5 s statement timeout).

## Alternatives rejected

- **Exclude every cancelled line and subtract chargebacks at the order level** - counts a
  chargeback-cancelled line twice (ADR-024's open item).
- **Date refunds by their own date** - splits one line's figure over two periods and can make
  a period negative; the slice chose payment dating.
- **One SQL query joining orders, payments and refunds** - fastest, but a cross-context join
  (ADR-005); the ports keep each context's tables its own.
- **Analytics inside Engagement or Fulfillment** - revenue is neither, and a context of its own
  gets the architecture rules.
- **Materialised daily rollups** - a migration and a job for a figure the shop can compute on
  demand at its scale.

## Revisit when

- A 366-day report passes 5 s p95 (the statement timeout would start cutting single reads), or
  paid payments pass about 300,000: consider a daily rollup or a read replica.
- The 30-day window or the recent page passes 50 ms p95: add the partial index of plan §4.2.
- The owner wants refunds dated by their own day: add a second series rather than change d3.
