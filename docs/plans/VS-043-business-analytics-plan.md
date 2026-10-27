# VS-043 — Business Analytics: Implementation Plan

**Status:** IN PROGRESS on `vs-043-analytics`. Owner answers (2026-10-27): Q1-Q12 accepted as
recommended (see §10).
**Date:** 2026-10-27
**Planned against alembic head:** `eeed201dcfd2` (`reviews_and_badge_index`, VS-036).
- Derived statically from `revision` / `down_revision` across the 33 files in
  `migrations/versions/`: one linear chain, one head, no merge revisions. VS-037 added no
  migration (`vertical-slice-plan.md:1088`).
- This slice plans **no migration** (D9, §4). If the CP1 measurement crosses the trigger, the
  one new revision gets `down_revision = "eeed201dcfd2"`. Re-derive the head just before
  `alembic revision`.

**Pre-flight (2026-10-27):** `git fetch`, `git checkout main`, `git pull --ff-only` (already
up to date at `131949a`, "Merge pull request #45 … vs-037-moderation"). There are 28 remote
branches. None mentions VS-043, analytics or export. The only untracked file is
`package-lock.json` (ignored). Highest ADR on `origin/main`: **ADR-044**. This slice takes
**ADR-045** (D14, Q10).

**Format:** follows [`VS-037-review-moderation-plan.md`](VS-037-review-moderation-plan.md).
Every `file:line` below is on `main` at `131949a`.

---

## 0. Decisions this plan takes (summary)

| # | Decision | Where |
|---|---|---|
| D1 | **Metric definitions are written first**, as api-endpoints §27.1, before any code (`vertical-slice-plan.md:1188`). §5 of this plan is that text. | §5, §8 step 1 |
| D2 | **Revenue = Σ over paid lines of (line total − counted refunds)**: line totals are the order-time snapshot (`order_items.line_total_cents`, `ordering/infrastructure/models.py:280`), there is no shipping (ADR-024 d1, `ADR-024…md:18`) and tax is 0. The **counted refunds** are pending and settled refund items plus chargeback items. Failed, voided and `late_capture` refunds never count (VS-030 plan `:683`; `vertical-slice-plan.md:1183`). A chargeback's excess is never put on a line. | §5.1 |
| D3 | **A chargeback is counted once: the exclusion side drops.** A cancelled line on a paid order is left out only when **nothing counts against it**, which is L2's "bare cancel" (`payments/domain/refunds.py:198`). A line the chargeback cancelled (ADR-042 d17, `ADR-042…md:70`) carries chargeback items, so it **stays a paid line** and its items net it to 0. Subtracted items and excluded lines are therefore disjoint by construction. This closes ADR-024's open item (`ADR-024…md:124-125`, `:140`). Test R9 proves it. | §5.2, Q1 |
| D4 | **Dated by the payment's `verified_at`** (`payments/infrastructure/models.py:72`). For cash, that is the handover: `insert_cash_payment` writes `verified_at = at` (`cash_payments.py:48-49`). A paid payment always has it (`ck_payments_paid_verified`, `models.py:120-123`). Refunds and chargebacks count against **their payment's** date, which is the slice's "dated by payment date" (`vertical-slice-plan.md:1189`). An earlier period therefore changes when a later refund lands. | §5.3, Q2 |
| D5 | **Day boundaries are `Asia/Beirut`.** `from` and `to` are calendar dates, both inclusive. They become a half-open UTC window, and the DST days are tested. | §5.4 |
| D6 | **Range errors answer 400 `INVALID_DATE_RANGE`** (a new §5.2 catalogue code): `to` before `from`, more than 366 days, or a year outside 2020-2100. A date that cannot be parsed stays the framework's 422. The funnel's 422 (`engagement/api/admin_analytics.py:83-92`) is a **separate follow-up** and is not changed here. | §2.1, Q6 |
| D7 | **A new `reporting` context** (`src/app/reporting/`), added to `CONTEXTS` (`tests/unit/test_deep_architecture.py:19-28`). It reads every context through a reporting function in that context's `public.py`, wrapped by a port. There is no cross-context SQL join, and the context imports only other contexts' `public` and `application.ports` (`:95-117`). | §3, Q4 |
| D8 | **One read-only snapshot per request.** A `report_session` dependency opens its own connection with REPEATABLE READ, READ ONLY and a 5 s `statement_timeout`. Every port reads the same snapshot, nothing can write, and a report never shares a transaction with an operational write (FR-18, `functional-requirements.md:978`). | §3.5 |
| D9 | **No migration unless measured.** CP1 seeds 100k payments and records p95 over 20 runs. If the 30-day window or the recent-purchases page is over **50 ms p95**, one additive partial index is added in its own reversible revision. | §4.2, Q5 |
| D10 | **A failing query is an error, never zeros.** No `try/except` returns a default. A database failure or timeout gives 503 `SERVICE_UNAVAILABLE` through the existing handler (`api/errors.py:136-157`), and anything else gives 500 (`:160-168`). A failure injected into each port proves it. | §2.1, §6.2 |
| D11 | **`refunded_cents_by_line` and `unsettled_refund_exists` are built here** in `app.payments.public`, as VS-030 plan §3.7 defines them (`VS-030…plan.md:683-684`). They are read-only and take no lock. A third function, `refund_covered_lines`, gives the D3 predicate. | §3.2 |
| D12 | **Boundary:** a new `admin_router` with `route_class=AdminBoundaryRoute`, mounted on `/api/v1/admin` (`api/v1/admin.py:91-96`). It inherits `require_admin` (MFA) and the 300/min admin limit (`:66-67`), and adds a **30/min per-admin analytics limit**. GET only, so there is no CSRF. **Reads are not audited** (no PII is shown). | §2, §5.9, Q7, Q8 |
| D13 | **No PII in any response:** no email, name, phone or address, only `user_id`. | §2.2 |
| D14 | **ADR-045 "Business analytics"** (new). It records the metric definitions, the reporting context, the read-only snapshot and the D3 rule, and amends ADR-024's open item. | §7, Q10 |

## 1. Scope and non-goals

### In scope (VS-043 only)

- `GET /api/v1/admin/analytics/overview`, `/revenue`, `/recent-purchases`, `/customers`,
  `/top-rated-products`, `/stl-sales` (`vertical-slice-plan.md:1186`;
  `api-endpoints.md:691-697`).
- F-120 revenue by stream, attributed per line, with cash counted when it is recorded; F-121
  recent purchases; F-122 pending offers count; F-124 best-selling STL (paid, unrefunded lines);
  F-125 top rated; F-126 customer statistics (`SRS.md:489-495`). SRS §15.5 (`SRS.md:984-988`),
  BR-149 (`SRS.md:344`), FR-18 (`functional-requirements.md:953-954`, `:978-979`).
- `refunded_cents_by_line`, `refund_covered_lines` and `unsettled_refund_exists` in
  `app.payments.public` (D11).

The seven analytics reports of api-endpoints §27 (`:691-697`) are the six new routes below
plus the existing wishlist route, which keeps its shape. The funnel (`:698`) is VS-035's.

| Endpoint | Status |
|---|---|
| `/analytics/overview`, `/revenue`, `/recent-purchases`, `/customers`, `/top-rated-products`, `/stl-sales` | **new** (this slice) |
| `/analytics/wishlist` (VS-038) | exists (`engagement/api/admin_analytics.py:35-61`); unchanged |
| `/analytics/custom-requests/funnel` (VS-035) | exists; 422 → 400 is a follow-up (D6) |

### Non-goals, and who owns them

| Not here | Owner | Why |
|---|---|---|
| Customer data export | VS-044 | A separate slice (`vertical-slice-plan.md:1202`). |
| Account deletion and its BR-126 check | VS-045 | Only the read `unsettled_refund_exists` is built here (D11). |
| CSV / spreadsheet export of reports | none in V1 | "Export formats" is an open design-time item (`SRS.md:1631`). |
| Materialised tables, nightly rollups | none in V1 | The slice says "Model / migration: None" (`vertical-slice-plan.md:1185`). Revisit if the §4.2 budget fails. |
| "As-of" revenue (each refund dated by its own date) | none in V1 | D4 follows the slice. Q2 asks the owner. |
| Download statistics | removed | ADR-019 (`vertical-slice-plan.md:1175-1177`). |
| Changing the funnel's 422 | follow-up | D6. |
| Currency conversion | none | Every line, refund and chargeback is USD (`ck_refunds_currency`, `models.py:301-304`; `ck_chargebacks_currency`, `:415`). A non-USD `late_capture` refund never counts (D2). |

---

## 2. API

All routes sit under `/api/v1/admin/analytics`, behind `require_admin` and `admin_rate_limit`
(`api/v1/admin.py:91-96`). The answers:
- no session → 401 `AUTH_REQUIRED`;
- customer → 404 `NOT_FOUND`, byte-identical to an imaginary path;
- admin without MFA → 401 `MFA_REQUIRED` (`api/v1/admin.py:16-19`).

### 2.1 Common rules

- **Range** (`overview`, `revenue`, `customers`, `stl-sales`):
  - `from: date?` and `to: date?` (`YYYY-MM-DD`, Beirut calendar days, both inclusive);
  - `to` defaults to today in Beirut, and `from` to `to − 29 days` (30 days);
  - 400 `INVALID_DATE_RANGE`, with `errors[0].loc = ["query", "<field>"]` (the `invalid_query`
    shape, `queue_cursor.py:43-46`), when `to < from`, the span is over 366 days, or a year
    falls outside 2020-2100. The year check keeps `end + 1 day` from overflowing;
  - 422 `VALIDATION_ERROR` for an unparseable date or an unknown `group_by` (FastAPI's own
    check, unchanged).
- **Money:** integer `*_cents` with one `currency: "USD"` per body, the same as the funnel
  (`admin_analytics.py:96-110`). Every report carries `timezone: "Asia/Beirut"`.
- **Errors:** 503 `SERVICE_UNAVAILABLE` for a database failure or timeout, 500 `INTERNAL_ERROR`
  otherwise (D10). A body with figures is never returned after a failed query.
- **Limit:** 429 `RATE_LIMITED` from the admin limit (300/min) and the analytics limit (30/min
  per admin, D12). Both are documented on every route.
- **Responses map:** `401`, `404`, `429`, `503` on all routes; `400` and `422` on the ranged
  and paged ones.

### 2.2 Schemas (`reporting/api/schemas.py`)

```text
StreamCents        { physical_cents: int, stl_cents: int, total_cents: int }
RevenueFigures     { gross: StreamCents, refunded: StreamCents, net: StreamCents,
                     paid_lines: int, paid_orders: int }
RevenueBucket      { start: date, net: StreamCents }
RevenueAnalytics   { from: date, to: date, timezone: str, group_by: day|week|month,
                     currency: "USD", totals: RevenueFigures, buckets: list[RevenueBucket],
                     unattributed_chargeback_excess_cents: int }
PendingOfferCounts { awaiting_admin: int, awaiting_customer: int, accepted: int, total: int }
AnalyticsOverview  { from, to, timezone, currency, net: StreamCents, paid_orders: int,
                     buyers: int, new_customers: int, pending_offers: PendingOfferCounts,
                     stl_lines_awaiting_delivery: int }
CustomerAnalytics  { from, to, timezone, currency, registered_customers: int,
                     new_customers: int, buyers: int, repeat_buyers: int,
                     net_per_buyer_cents: int | null }
StlSalesItem       { product_id, name: str, slug: str | null, units: int, lines: int,
                     net_cents: int, awaiting_delivery: int }
StlSalesAnalytics  { from, to, timezone, currency, items: list[StlSalesItem],
                     stl_lines_awaiting_delivery: int }
TopRatedProduct    { product_id, name, slug, type: physical|stl, average_rating: Decimal,
                     review_count: int, is_visible: bool }
TopRatedProductList { items: list[TopRatedProduct] }
RecentPurchase     { order_id, order_number, user_id, paid_at: datetime,
                     payment_method: online|cash, gross: StreamCents, refunded_cents: int,
                     net_cents: int, paid_lines: int }
RecentPurchasePage { items: list[RecentPurchase], next_cursor: str | null }
```

`buckets` lists every bucket in the range, including empty ones: a computed zero is a true
figure, not a fabricated one (D10 is about failures). `from` is serialised by alias, as the
funnel does (`from_` with `alias="from"`).

### 2.3 Per route

| Route | Query | Notes |
|---|---|---|
| `GET /overview` | range | Net by stream, paid orders, buyers and new customers in range. Pending offers and STL lines awaiting delivery are **now** (not ranged). |
| `GET /revenue` | range, `group_by` (default `day`) | D2-D5. `week` starts on Monday (ISO). A bucket is clipped to the range at both ends. |
| `GET /recent-purchases` | `cursor`, `limit` (default 20, 1-100) | Newest `verified_at` first, keyset `(verified_at, payment_id)` descending. An unpaid cash order is absent; a cash order appears at its handover. A tampered cursor gives 422 (the `invalid_query` precedent). No range. |
| `GET /customers` | range | §5.7. |
| `GET /stl-sales` | range, `limit` (default 20, 1-100) | §5.6. |
| `GET /top-rated-products` | `limit` (default 20, 1-100), `min_reviews` (default 3, 1-1000) | §5.8. No range: the aggregates have no time dimension (as wishlist, `admin_analytics.py:1-2`). |

---

## 3. Layers, function by function

### 3.1 The `reporting` context (D7)

```text
src/app/reporting/
  domain/metrics.py         pure: Stream, GroupBy, RangeError, ReportLine, LineRevenue,
                            is_paid_line, report_window, local_day, bucket_start, summarise
  application/ports.py      Protocols + row dataclasses (below)
  application/reports.py    revenue_report, overview, customer_stats, stl_sales,
                            recent_purchases, top_rated
  infrastructure/adapters.py  one adapter per port; each calls only <context>.public
  api/schemas.py, api/admin_analytics.py, api/session.py
  public.py                 empty for now (no consumer)
```

The domain imports only the standard library (`zoneinfo`, `datetime`, `dataclasses`). The
application layer imports only the domain, and the infrastructure only other contexts'
`public`. `tests/unit/test_deep_architecture.py` gains `"reporting"` in `CONTEXTS` (`:19-28`),
so every rule there applies to it.

```python
BEIRUT: Final = ZoneInfo("Asia/Beirut")
MAX_SPAN_DAYS: Final = 366
DEFAULT_SPAN_DAYS: Final = 30
EARLIEST: Final = date(2020, 1, 1)
LATEST: Final = date(2100, 12, 31)


class Stream(StrEnum):
    PHYSICAL = "physical"
    STL = "stl"


class GroupBy(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class RangeError(ValueError):
    """The router turns it into 400 INVALID_DATE_RANGE naming `field`."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


@dataclass(frozen=True)
class ReportLine:
    id: UUID
    order_id: UUID
    user_id: UUID
    product_id: UUID
    name_snapshot: str
    stream: Stream
    status: str
    quantity: int
    line_total_cents: int

    @property
    def cancelled(self) -> bool:
        return self.status == "cancelled"


@dataclass(frozen=True)
class LineRevenue:
    line: ReportLine
    paid_on: date
    refunded_cents: int

    @property
    def net_cents(self) -> int:
        return self.line.line_total_cents - self.refunded_cents


def is_paid_line(line: ReportLine, *, covered: bool) -> bool:
    """BR-149 on a paid order: a cancelled line is unpaid only when nothing counts against it
    (L2's bare cancel), so a chargeback-cancelled line stays paid and nets to 0 (D3)."""
    return not line.cancelled or covered


def report_window(start: date, end: date) -> tuple[datetime, datetime]:
    """Inclusive Beirut calendar days to a half-open UTC window [lower, upper)."""
    for field, day in (("from", start), ("to", end)):
        if not EARLIEST <= day <= LATEST:
            raise RangeError(field, f"must be between {EARLIEST} and {LATEST}")
    if end < start:
        raise RangeError("to", "must not be before from")
    if (end - start).days + 1 > MAX_SPAN_DAYS:
        raise RangeError("to", f"the range may span at most {MAX_SPAN_DAYS} days")
    lower = datetime.combine(start, time.min, BEIRUT)
    upper = datetime.combine(end + timedelta(days=1), time.min, BEIRUT)
    return lower.astimezone(UTC), upper.astimezone(UTC)


def local_day(moment: datetime) -> date:
    return moment.astimezone(BEIRUT).date()


def bucket_start(day: date, group_by: GroupBy) -> date:
    if group_by is GroupBy.WEEK:
        return day - timedelta(days=day.weekday())
    if group_by is GroupBy.MONTH:
        return day.replace(day=1)
    return day
```

- Lebanon moves its clocks at 00:00 local time. On the spring day, midnight does not exist;
  `zoneinfo` with `fold=0` resolves it to the transition instant, which is when that day
  starts. Unit tests pin 2026-03-29 (23 h) and 2026-10-24 (25 h): Lebanon falls back at
  Sunday 00:00 +03 to Saturday 23:00 +02, so the long day is the Saturday, and 2026-10-25 is
  24 h, starting where 2026-10-24 ends (corrected 2026-10-27; the plan first said 10-25).
- **No clamp** on `net_cents`. A negative line would be a money bug, and R16 asserts it never
  happens; hiding it would breach D10's spirit.
- `summarise(facts, *, start, end, group_by, excess_cents) -> RevenueReport` is pure. It builds
  totals by stream (gross, refunded, net, paid lines, distinct paid orders) and one bucket per
  `bucket_start` from `start` to `end`, zero-filled and clipped.
- `tzdata` joins the runtime dependencies in `pyproject.toml`. Today nothing uses `zoneinfo`
  (no `ZoneInfo` in `src/app`), and Windows and slim images have no system database (R3).

### 3.2 Published reads added to other contexts (`public.py`, all unlocked, read-only)

| Context | Function | SQL / index |
|---|---|---|
| Payments | `refunded_cents_by_line(session, line_ids) -> dict[UUID, int]` | refund items ⋈ refunds (`ix_refund_items_order_item`, `models.py:376`) + chargeback items (`ix_chargeback_items_order_item`, `:447`) |
| Payments | `refund_covered_lines(session, line_ids) -> frozenset[UUID]` | the same, with `is_counted`'s predicate (adds a failed, not reissued refund) |
| Payments | `unsettled_refund_exists(session, user_id) -> bool` | `ix_refunds_order` (`models.py:351`) via the user's order ids |
| Payments | `paid_payments_between(session, lower, upper) -> list[PaidPaymentRow]` | `status IN REACHED_PAID AND verified_at ∈ [lower, upper)`; seq scan today (§4.2) |
| Payments | `paid_payment_page(session, *, before, limit) -> list[PaidPaymentRow]` | the same predicate, `ORDER BY verified_at DESC, id DESC LIMIT n` |
| Payments | `chargeback_excess_cents(session, payment_ids) -> int` | `ix_chargebacks_payment` (`models.py:423`) |
| Ordering | `report_lines(session, order_ids) -> list[ReportLineRow]` | `ix_order_items_order_id` (`ordering/infrastructure/models.py:394`) |
| Ordering | `order_ids_for_user(session, user_id) -> list[UUID]` | `ix_orders_user_placed` (`:223`) |
| Ordering | `stl_awaiting_delivery_counts(session) -> dict[UUID, int]` | `ix_order_items_stl_awaiting` (`:401-408`), by product |
| Ordering | `orders_by_id` (exists, `ordering/public.py:700-702`) | order number and method for recent purchases |
| Negotiation | `live_offer_counts(session) -> dict[OfferStatus, int]` | `LIVE_SQL` statuses (`negotiation/infrastructure/models.py:26`), `ix_offers_status_responds_by` (`:109`) |
| Catalog | `top_rated_products(session, *, limit, min_reviews) -> list[RatedProductRow]` | live products, `review_count >= min`, `average_rating DESC, review_count DESC, id`; seq scan of `products` |
| Catalog | `product_labels(session, ids) -> dict[UUID, ProductLabel]` | by primary key; name and slug (null when deleted) |
| Identity | `customer_counts(session, *, created_from, created_to) -> CustomerCounts` | `users` count, filtered |

Payments' SQL (`payments/infrastructure/reports.py`, new; it joins only Payments' own
tables):

```python
_CHUNK = 5_000
_NOT_LATE = RefundModel.kind != RefundKind.LATE_CAPTURE
# Plan 3.7: what revenue subtracts. Pending and settled only; never failed, voided or late.
_REVENUE_COUNTED = _NOT_LATE & RefundModel.status.in_((RefundStatus.PENDING, RefundStatus.SETTLED))
# `is_counted` (domain/refunds.py:179-183) in SQL: also a failed refund not yet reissued.
_COVERAGE_COUNTED = _NOT_LATE & (
    RefundModel.status.in_((RefundStatus.PENDING, RefundStatus.SETTLED))
    | ((RefundModel.status == RefundStatus.FAILED) & RefundModel.reissued_at.is_(None))
)
# `ix_refunds_obligations`' predicate, any kind (BR-126, VS-045 note).
_OBLIGATION = (RefundModel.status == RefundStatus.PENDING) | (
    (RefundModel.status == RefundStatus.FAILED) & RefundModel.reissued_at.is_(None)
)


async def refunded_cents_by_line(
    session: AsyncSession, line_ids: Sequence[UUID]
) -> dict[UUID, int]:
    """Pending and settled refund items plus chargeback items, per line. Unlocked: a report
    reads it and never decides money (ADR-042 d14)."""
    out: defaultdict[UUID, int] = defaultdict(int)
    for chunk in _chunks(line_ids):
        refunded = (
            select(RefundItemModel.order_item_id, func.sum(RefundItemModel.amount_cents))
            .join(RefundModel, RefundModel.id == RefundItemModel.refund_id)
            .where(RefundItemModel.order_item_id.in_(chunk), _REVENUE_COUNTED)
            .group_by(RefundItemModel.order_item_id)
        )
        charged = (
            select(ChargebackItemModel.order_item_id, func.sum(ChargebackItemModel.amount_cents))
            .where(ChargebackItemModel.order_item_id.in_(chunk))
            .group_by(ChargebackItemModel.order_item_id)
        )
        for query in (refunded, charged):
            for line_id, cents in await session.execute(query):
                out[line_id] += int(cents)
    return dict(out)


async def unsettled_refund_exists(session: AsyncSession, user_id: UUID) -> bool:
    """A pending refund, an owed one, or a pending late_capture on any of the user's orders.
    Unlocked: VS-045 calls it again under its own user and order locks."""
    order_ids = await order_ids_for_user(session, user_id)
    for chunk in _chunks(order_ids):
        query = select(exists().where(RefundModel.order_id.in_(chunk), _OBLIGATION))
        if (await session.execute(query)).scalar():
            return True
    return False
```

- **Why the three predicates differ:**
  - `_REVENUE_COUNTED` is plan §3.7's: only money returned or about to be.
  - `_COVERAGE_COUNTED` is L1's `is_counted` (`domain/refunds.py:179-183`), which also counts
    the failed, not-reissued amount it reserves. The bare-cancel test (D3) must use L1, so that
    it matches `line_balances` (`:191-201`).
  - `_OBLIGATION` is BR-126's "unsettled". It includes a pending or failed `late_capture`
    refund, exactly as `ix_refunds_obligations` (`models.py:343-350`) and the slice note
    (`vertical-slice-plan.md:1221`) define it. A settled or voided one is not unsettled.
- **Voided refunds never double-count against a chargeback.** A chargeback voids the open
  refunds and takes over their items (ADR-042 d16, `ADR-042…md:69`). The voided refund leaves
  every predicate, and its amount shows up once, as a chargeback item.
- `_chunks` caps each `IN` list at 5,000, well under asyncpg's 32,767 bind parameters.
- R16 proves SQL/domain parity: one refund of each `(kind, status, reissued)` combination,
  with `is_counted` asserted on the same rows.
- `unsettled_refund_exists` reads `app.ordering.public.order_ids_for_user`. Payments already
  imports `app.ordering.public` (`payments/public.py:11`).

### 3.3 Ports (`reporting/application/ports.py`)

| Port | Methods |
|---|---|
| `PaidPayments` | `paid_payments(lower, upper)`, `page(before, limit)`, `chargeback_excess_cents(payment_ids)` |
| `LineRefunds` | `refunded_cents_by_line(line_ids)`, `covered_lines(line_ids)` |
| `OrderLines` | `order_lines(order_ids)`, `orders(order_ids)`, `stl_awaiting_delivery_counts()` |
| `OfferCounts` | `live_counts()` |
| `ProductRatings` | `top_rated(limit, min_reviews)`, `labels(ids)` |
| `CustomerCounts` | `counts(created_from, created_to)` |

`RevenueReads` is the intersection protocol `PaidPayments + LineRefunds + OrderLines` that
`revenue_report` takes. Row types (`PaidPayment(id, order_id, provider, verified_at)`,
`ReportLine`, and the others) are reporting domain dataclasses. The adapters map other
contexts' rows onto them, so no other context's type crosses the port.

### 3.4 Application (`reporting/application/reports.py`)

```python
async def revenue_report(
    reads: RevenueReads, *, start: date, end: date, group_by: GroupBy
) -> RevenueReport:
    """One snapshot (the caller's REPEATABLE READ session); no cross-context join."""
    lower, upper = report_window(start, end)
    paid = await reads.paid_payments(lower, upper)
    facts, excess = await paid_line_revenue(reads, paid)
    return summarise(facts, start=start, end=end, group_by=group_by, excess_cents=excess)


async def paid_line_revenue(
    reads: RevenueReads, paid: Sequence[PaidPayment]
) -> tuple[list[LineRevenue], int]:
    """Every paid line of these payments' orders, with its refunds, and the excess."""
    paid_on = {payment.order_id: local_day(payment.verified_at) for payment in paid}
    lines = await reads.order_lines(list(paid_on))
    line_ids = [line.id for line in lines]
    refunded = await reads.refunded_cents_by_line(line_ids)
    covered = await reads.covered_lines(line_ids)
    facts = [
        LineRevenue(line, paid_on[line.order_id], refunded.get(line.id, 0))
        for line in lines
        if is_paid_line(line, covered=line.id in covered)
    ]
    excess = await reads.chargeback_excess_cents([payment.id for payment in paid])
    return facts, excess
```

- **One paid payment per order:** `uq_payments_one_live` (`models.py:141-146`) allows one
  non-failed, non-expired payment per order, and `paid_payment` relies on it
  (`domain/refunds.py:166-168`). So `paid_on` is keyed safely by `order_id`, and a failed
  attempt beside a paid retry adds nothing (R8).
- `overview` = `paid_line_revenue` totals + `customer_counts` + `live_counts` +
  `stl_awaiting_delivery_counts`.
- `customer_stats`: buyers and repeat buyers come from the same `LineRevenue` facts, grouped by
  `line.user_id` and distinct `order_id`.
- `stl_sales`: the facts filtered to `Stream.STL` and `line.status in {"awaiting_delivery",
  "delivered"}` ("paid, unrefunded", `SRS.md:493`). They are grouped by `product_id` and
  ranked `units DESC, net_cents DESC, product_id`, then labelled through `ProductRatings.labels`
  (falling back to the snapshot name), and joined with the per-product awaiting-delivery
  counts.
- `recent_purchases`: `page(before, limit + 1)` → `paid_line_revenue` for those payments only →
  `orders(order_ids)` for `order_number` and method.
- `top_rated`: a direct pass-through.

### 3.5 API (`reporting/api/`)

- `admin_router = APIRouter(prefix="/analytics", tags=["admin"], route_class=AdminBoundaryRoute)`,
  copying `engagement/api/admin_analytics.py:21`. Two routers share the prefix; their paths do
  not overlap.
- `api/v1/admin.py`: `router.include_router(business_analytics_router)` with a one-line
  `# VS-043` comment, the same as `:115-116`.
- Each route: `dependencies=[Depends(analytics_rate_limit)]`, which depends on `require_admin`
  as `admin_rate_limit` does (`api/v1/admin.py:72-88`); key prefix `admin_analytics`, 30 per
  60 s. Then `session = Depends(report_session)`, build the adapters, call the report and map
  `RangeError` → `ApiError(400, "INVALID_DATE_RANGE", …)`.
- `report_session` (`reporting/api/session.py`):

```python
async def report_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """Its own connection: READ ONLY, REPEATABLE READ (one snapshot for every port) and a
    statement timeout, so a report never writes and never holds an operational transaction."""
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        await session.connection(
            execution_options={"isolation_level": "REPEATABLE READ", "postgresql_readonly": True}
        )
        await session.execute(text(f"SET LOCAL statement_timeout = {REPORT_TIMEOUT_MS}"))
        try:
            yield session
        finally:
            await session.rollback()
```

- It is a separate session from `get_session`, because `require_admin` has already queried
  that one (`app/api/dependencies.py:7-22`), and `SET TRANSACTION` must come first.
- A read-only REPEATABLE READ transaction never fails with a serialisation error.
- `REPORT_TIMEOUT_MS = 5_000` (Q8).
- **UNVERIFIED** until step 6: that `postgresql_readonly` takes effect on the asyncpg dialect.
  The fallback is `SET TRANSACTION READ ONLY` as the first statement.
- **UNVERIFIED** until step 6: that asyncpg's `QueryCanceledError` reaches the handler as
  `sqlalchemy.exc.OperationalError` (giving 503). If it arrives as another `DBAPIError`, the
  router maps the timeout to 503 explicitly. Either way the answer is an error (D10).

---

## 4. Database

### 4.1 Migration: none planned (D9)

- Every read uses existing columns and indexes (§3.2). No write anywhere. The single head
  stays `eeed201dcfd2`.
- The CP1 measurement can change this, and only by adding one index.

### 4.2 The paid-payments index (Q5)

| Query | Plan with today's indexes |
|---|---|
| M1 `paid_payments_between`, 30-day window | Seq scan of `payments`. No index leads with `verified_at`; `ix_payments_unsettled` covers only pending and processing (`models.py:154-159`). |
| M2 the same, 366-day window | Seq scan; about a third of the rows qualify. Recorded, not a trigger: an index barely helps a scan of that selectivity. |
| M3 `paid_payment_page`, first and deep keyset | Seq scan + top-N heapsort (`LIMIT 21`) |
| M4 `report_lines`, 5,000 order ids | `ix_order_items_order_id` |
| M5 / M6 refund and chargeback items, 5,000 line ids | `ix_refund_items_order_item`, `ix_chargeback_items_order_item` |
| M7 whole `GET /revenue`, 366 days | end-to-end route time |

- **Seed (CP1):**
  - 100,000 payments over three years: 90% reached paid (cash 30%, verified at "handover");
    10% failed, expired or pending;
  - one to three lines per order (about 200k lines, 40% STL);
  - 10% of orders with a refund, of mixed status, and 1% with a chargeback.
- **Method:** `EXPLAIN (ANALYZE, BUFFERS)` for M1-M6, and 20 runs each with p50 and p95,
  on the test container (`postgres:16`, `docker-compose.yml:6`).
- **Trigger:** M1 or M3 over **50 ms p95** adds, in one revision with
  `down_revision = "eeed201dcfd2"`:
  `CREATE INDEX ix_payments_reached_paid_verified ON payments (verified_at DESC, id DESC)
  WHERE status IN ('paid', 'partially_refunded', 'refunded')`.
  It ships with a `drop_index` downgrade and the matching `Index(...)` in
  `PaymentModel.__table_args__` for the parity test.
  - It is additive, reversible and backward compatible.
  - It serves M1 (range) and M3 (ordered keyset) with one index.
  - A composite `(status, verified_at)` would need three range scans and a sort for M3's
    `ORDER BY`, because `status IN (…)` has three values. Q5 asks which one, if any.
- **Budget, recorded but not a migration trigger:** M7 at 366 days should stay under 2 s p95.
  If it does not, that goes to the owner with the numbers (materialising is a non-goal).

---

## 5. Metric definitions (written first; api-endpoints §27.1)

### 5.1 Revenue (F-120, SRS §15.5)

For a range `[from, to]` of Beirut calendar days:
1. Take every payment that **reached paid** (`paid`, `partially_refunded`, `refunded`;
   `payments/domain/enums.py:6-16`) whose `verified_at` falls in the window. There is at most
   one per order.
2. Take every line of those orders that is a **paid line** (§5.2).
3. **gross** = Σ `line_total_cents` (the order-time snapshot). There is no shipping and the tax
   is 0 (ADR-024 d1).
4. **refunded** = Σ of the line's items in refunds with status `pending` or `settled` and kind
   `admin` or `cancellation`, plus its chargeback items.
5. **net** = gross − refunded, attributed **per line** to its stream (`physical` or `stl`,
   from `product_type`).
6. Never counted: a `failed` refund (until its reissue, which counts), a `voided` refund, any
   `late_capture` refund, and a chargeback's `excess_cents`. The excess is shown separately as
   `unattributed_chargeback_excess_cents` and never subtracted (Q12).

### 5.2 Paid line (BR-149, ADR-024 d11 `:44`)

A line of an order whose payment reached paid, **unless** it is `cancelled` with nothing
counting against it. "Counting" here means an item in a pending, settled, or failed-and-not-
reissued refund (not `late_capture`), or a chargeback item: the exact `is_counted` / L2 rule
(`domain/refunds.py:179-201`). Consequences:
- An unpaid cash order has no payment row (ADR-024 d3), so it adds nothing.
- A cash line refused before the handover is cancelled with no refund, so it is not a paid
  line (`SRS.md:810`).
- A line cancelled after payment always carries its cancellation refund (ADR-043 d1), so it
  appears in gross and nets to its unreturned part.
- A line cancelled by a chargeback (ADR-042 d17) carries the chargeback's items, so it appears
  once in gross and nets to 0. **The chargeback is counted once** (D3).

### 5.3 Dating (D4)

Each line, with all its refunds and chargeback items, belongs to the Beirut day of its
payment's `verified_at`. For cash, that is the handover. A refund recorded later therefore
lowers the figure of the day the money came in, so past periods can change. This is the
slice's "dated by payment date" (`vertical-slice-plan.md:1189`).

### 5.4 Days and ranges (D5, D6)

Days are `Asia/Beirut` calendar days, with DST handled by `zoneinfo`. `from` and `to` are
inclusive and span at most 366 days. A week starts on Monday, and a month on day 1.

### 5.5 Recent purchases (F-121)

Payments that reached paid, newest `verified_at` first, with each order's paid-line gross by
stream, refunded and net (§5.1 per order).

### 5.6 Best-selling STLs (F-124)

Paid STL lines in the range (§5.1 dating) whose status is still `awaiting_delivery` or
`delivered`. A `refunded` or cancelled line is excluded, so "a refund of the rest removes the
line entirely" (`vertical-slice-plan.md:1197`).
- Each product shows `units` (Σ quantity), `lines`, and `net_cents` after partial refunds.
- `awaiting_delivery` is the product's count now, and the report also carries the global
  queue count (`api-endpoints.md:696`).

### 5.7 Customer statistics (F-126)

- `registered_customers`: users with role `customer`, email verified, not anonymised and not
  deleted. This is a count **now**.
- `new_customers`: the same filter, created in the range.
- `buyers`: distinct `user_id` with at least one paid line in the range (§5.1 dating).
- `repeat_buyers`: buyers with at least two distinct paid orders in the range.
- `net_per_buyer_cents` = ⌊net ÷ buyers⌋, or null with no buyers.

### 5.8 Top rated (F-125) and pending offers (F-122)

- **Top rated:** products not deleted with `review_count >= min_reviews`, by the maintained
  `average_rating` (exact over live, visible reviews; VS-036 plan `:460`), then
  `review_count`, then `id`.
  - Hidden-but-live products are included, flagged `is_visible` (the wishlist precedent,
    `product_repository.py:145-146`).
- **Pending offers:** live offers by status now: `awaiting_admin`, `awaiting_customer`,
  `accepted` (`LIVE_SQL`). `total` is their sum.

### 5.9 What is never shown

No email, name, phone, address, provider reference, dispute reference or note. Reads are not
audited (Q7): the precedent is the admin order queue, whose reads are not audited
(`fulfillment/api/admin_orders.py` audits only its writes) and VS-037 Q4.

---

## 6. Tests

[M] = must-have for the checkpoint. [N] = nice-to-have, added if cheap.

### 6.1 Unit (`tests/unit/reporting/`)

- `test_metrics.py`:
  - [M] `is_paid_line`: live → True; cancelled, not covered → False; cancelled and covered →
    True.
  - [M] `report_window`:
    - 2026-10-01..2026-10-01 → `[2026-09-30T21:00Z, 2026-10-01T21:00Z)`;
    - spring day 2026-03-29 is 23 h, autumn day 2026-10-24 (Saturday) is 25 h, and 2026-10-25
      is 24 h starting where 10-24 ends;
    - 366 days pass and 367 fail on `to`;
    - `to < from` fails;
    - 2019-12-31 and 2101-01-01 fail on their field.
  - [M] `bucket_start` for day, week (a Sunday maps to the Monday before) and month.
  - [M] `summarise`:
    - a mixed order splits by stream;
    - buckets are zero-filled and clipped at both ends;
    - `paid_orders` counts distinct orders;
    - excess is carried, not subtracted.
- `test_reports.py` (fakes for every port, as `test_review_service.py` does):
  - [M] `revenue_report` calls the ports in this order: `paid_payments` → `order_lines` →
    `refunded_cents_by_line` → `covered_lines` → `chargeback_excess_cents`. Nothing else.
  - [M] **Every port raising propagates** (no `except`), for each of the six reports (D10).
  - [M] `stl_sales` excludes refunded and cancelled lines, ranks, and falls back to the
    snapshot name.
  - [M] `customer_stats` counts buyers and repeat buyers; `net_per_buyer` is null at zero
    buyers.

### 6.2 Integration, real Postgres (`tests/integration/reporting/test_revenue_api.py` and siblings)

The scenarios are built through the real money paths (checkout, verification, cash handover,
refund create/settle/fail/reissue/void, chargeback), reusing
`tests/integration/payments/refund_support.py`. Each asserts the exact cents.

- [M] **R1 mixed order:** online, physical 100.00 + STL 40.00, paid → physical 10,000,
  STL 4,000, total 14,000.
- [M] **R2 partial refund** of 25.00 on the physical line, pending → physical net 7,500. After
  settle, still 7,500.
- [M] **R3 cash:**
  - unpaid cash order → nothing in the range;
  - the handover recorded at 22:30Z on 2026-10-01 → the bucket is **2026-10-02** in Beirut,
    not the placement day.
- [M] **R4 partly refused cash order:** one line refused (`ready_to_ship → cancelled`,
  `refused`), the rest handed over → only the handed-over lines count, and the refused one is
  absent from gross.
- [M] **R5 partial-amount refund:**
  - 30.00 of an 80.00 line → that line's net is 5,000, and the other lines are unchanged;
  - a second refund of the remaining 50.00 → the line nets 0, and it is gone from `/stl-sales`
    when it is an STL line (status `refunded`).
- [M] **R6 failed refund:**
  - pending 20.00 then failed → it reduces nothing;
  - reissued (the reissue pending) → it reduces 2,000 again;
  - the reissue settled → 2,000.
- [M] **R7 voided refund** → it reduces nothing.
- [M] **R8 late capture:**
  - attempt A fails, then a late capture creates a pending `late_capture` refund;
  - retry B is paid;
  - revenue counts B's lines once; the late-capture refund appears nowhere; the totals equal
    B's lines.
- [M] **R9 chargeback counted once (D3):** online, physical 100.00 (`in_production`) + STL
  50.00, paid. A chargeback of 100.00 on the physical line cancels it (ADR-042 d17).
  - Expected: physical gross 10,000, refunded 10,000, net 0; STL 5,000; total net **5,000** =
    paid 15,000 − charged 10,000.
  - The "excluded and subtracted" double count would give 0. Dropping the chargeback would
    give 15,000. Both are asserted against.
  - **Mutation proof:** changing `is_paid_line` to `not line.cancelled` makes R9 fail.
- [M] **R9b partial chargeback, then cancel:**
  - a chargeback of 60.00 on the 100.00 physical line;
  - the admin cancels the line → a cancellation refund of 40.00 (`create_cancellation_refund`)
    → physical net 0;
  - that refund then fails → physical net **4,000** (money still held), and the line is still a
    paid line (covered by an owed refund).
- [M] **R9c chargeback after a full refund:** net 0 (not negative), and
  `unattributed_chargeback_excess_cents` = the charge.
- [M] **R10 a chargeback absorbing a pending refund** (ADR-042 d16): the voided refund and the
  chargeback item are not both subtracted. The net equals total − charged.
- [M] **R11 dating:** paid on 2026-09-15, refunded on 2026-10-05 → September's bucket drops,
  and October's is unaffected.
- [M] **R12 ranges:**
  - `to < from` → 400 `INVALID_DATE_RANGE` with `loc ["query","to"]`;
  - 367 days → 400;
  - year 2101 → 400;
  - `from=garbage` → 422;
  - no range → the last 30 days ending today in Beirut.
- [M] **R13 failure is an error:**
  - a monkeypatched port raising `OperationalError` → 503 and no `totals` key;
  - one raising `RuntimeError` → 500;
  - for each of the six routes.
  - [N] a real timeout: `REPORT_TIMEOUT_MS = 1` with `pg_sleep` in a patched query → 503.
- [M] **R14 read-only:** an `INSERT` through `report_session` raises
  (`read-only transaction`), and `SHOW transaction_isolation` is `repeatable read`.
- [M] **R15 USD and no shipping:** order total = Σ lines, and revenue = Σ lines for an
  unrefunded order.
- [M] **R16 SQL/domain parity and integrity:**
  - one refund of every `(kind, status, reissued)` combination;
  - `refunded_cents_by_line` equals the §3.7 rule, `refund_covered_lines` equals
    `is_counted`, and `unsettled_refund_exists` equals `_OBLIGATION`;
  - over all R-scenarios, no line's net is negative.
- [M] **`unsettled_refund_exists`:**
  - pending admin refund → True; owed failed → True;
  - failed + reissue settled → False; voided → False;
  - pending `late_capture` → True; settled `late_capture` → False;
  - another user's pending refund → False; no orders → False.
- [M] **Recent purchases:**
  - 45 paid payments, some with equal `verified_at`, pages of 20 → 45 distinct ids in
    `(verified_at, id)` descending order;
  - a tampered cursor → 422;
  - an unpaid cash order is absent, and a cash order is listed at its handover.
- [M] **STL sales:**
  - ranking;
  - a partially refunded line counted with net reduced;
  - an offer-bought line at its agreed price;
  - the per-product and global awaiting-delivery counts.
- [M] **Top rated:**
  - aggregates read as stored;
  - a review hidden through VS-037 drops the average;
  - a deleted product is absent; a hidden product is flagged;
  - `min_reviews` filters.
- [M] **Customers:** an anonymised user and an unverified user are not registered; buyers and
  repeat buyers.
- [M] **Overview:** offer counts by status; expired, withdrawn and paid offers are not
  counted; STL awaiting delivery.
- [M] **No PII:** no `email`, `phone`, `address` or `name_snapshot` key at any depth in any
  response. A string search for the seeded customer's email in every body.
- [N] **R17 snapshot:** a report paused between `paid_payments` and `refunded_cents_by_line`
  while a refund commits → it reports the pre-refund figure (REPEATABLE READ), never a mix.

### 6.3 Boundary and OpenAPI

- [M] `tests/integration/identity/test_deep_vs005_admin_mfa.py`: the matrix reads admin paths
  from `main_app.openapi()` (`:60-81`), so the six new GETs are covered with **no edit**.
  - Wrong methods (for example `POST /admin/analytics/revenue`) come through
    `_admin_wrong_methods`.
  - Run it at CP1. `len(ADMIN_OPERATIONS) >= 15` (`:107-108`) only grows.
- [M] `tests/integration/test_openapi_security.py`: a new `VS043_ROUTES` (six GETs) and a test
  copied from VS-037 (`:176-197`):
  - `security == [{"sessionCookie": []}]`;
  - `{"401", "404", "429", "503"}` in the responses;
  - `{"400", "422"}` on the ranged and paged routes.
- [M] A customer gets 404 identical to `IMAGINARY` on each route (covered by the matrix;
  asserted once directly for `/revenue`).
- [M] `tests/unit/test_openapi_snapshot.py`: regenerate `docs/frontend-handoff/openapi.json`.
  The diff adds only the six operations and the §2.2 schemas.
- [N] The analytics limit: the 31st request in 60 s → 429, while other admin routes still
  answer.

### 6.4 Static

- [M] `tests/unit/test_deep_architecture.py` with `"reporting"` in `CONTEXTS`: the domain is
  pure, the application imports domain only, and cross-context imports are only `public` /
  `application.ports`.
- [M] `ruff check`, `ruff format --check .`, `mypy --strict`.

---

## 7. Docs and ADRs

- **ADR-045 "Business analytics: per-line revenue from one read-only snapshot"** (new, D14,
  Q10):
  - d1 the metric definitions of §5;
  - d2 the D3 rule (a chargeback is counted once; the exclusion side drops);
  - d3 dating by `verified_at`, Beirut days;
  - d4 the `reporting` context and its ports, with no cross-context joins;
  - d5 `report_session` (read-only, REPEATABLE READ, 5 s timeout);
  - d6 400 `INVALID_DATE_RANGE`;
  - d7 the 30/min limit and the unaudited reads;
  - d8 the index decision as CP1 measured it.
  - "Amends ADR-024" (its VS-043 open item). README line added.
- **ADR-024:** strike through the VS-043 open items (`ADR-024…md:124-125`, `:140`) with
  "**Resolved** by ADR-045 d2".
- `docs/requirments/api-endpoints.md`:
  - §27 rows `:691-697` gain the query parameters, 400 `INVALID_DATE_RANGE`, 429 and 503;
  - new §27.1 "Metric definitions" (§5 of this plan, **written first**, step 1);
  - §5.2 gains `400 INVALID_DATE_RANGE`;
  - §30 gains the §2.2 schemas;
  - the funnel row `:698` gets a "follow-up: 422 → 400" note only.
- `docs/SRS.md`:
  - §15.5 (`:986`) gains "dated by the payment's verification (cash: handover), Beirut days;
    a line cancelled by a chargeback stays a paid line and nets to 0 (ADR-045)";
  - BR-149 (`:344`) gains the same clarification.
- `docs/requirments/database-design.md`: §9.1 only if the CP1 index is added.
- `docs/vertical-slice-plan.md`:
  - the row `:48` → Done;
  - the entry `:1179-1200` gains an "As built" block;
  - the VS-045 entry notes that `unsettled_refund_exists` exists (`:1221`).
- `docs/plans/VS-030-refunds-settlement-plan.md`: §3.7 `:683-684` gains "built in VS-043".
- `docs/frontend-handoff/`: `openapi.json` regenerated, plus one `BACKEND-RESPONSE.md` entry
  for the dashboard screens.
- This plan: Status → DONE at the end.

---

## 8. Implementation steps (one PR)

Each step is small and leaves the tree green. There is **one checkpoint**, at the end.

1. **Definitions first:** api-endpoints §27.1 (§5), §5.2 `INVALID_DATE_RANGE`, §27 rows, §30
   schemas. Docs only.
2. `reporting` skeleton:
   - `domain/metrics.py` and its unit tests (§6.1);
   - `tzdata` in `pyproject.toml`;
   - `"reporting"` in `CONTEXTS`.
3. Payments reads (`payments/infrastructure/reports.py` + `public.py` exports):
   `refunded_cents_by_line`, `refund_covered_lines`, `paid_payments_between`,
   `paid_payment_page`, `chargeback_excess_cents`, `unsettled_refund_exists`. Then R16 and
   the `unsettled_refund_exists` tests.
4. Ordering (`report_lines`, `order_ids_for_user`, `stl_awaiting_delivery_counts`),
   Negotiation (`live_offer_counts`), Catalog (`top_rated_products`, `product_labels`) and
   Identity (`customer_counts`) public reads, each with a small integration test.
5. Reporting ports, adapters and `reports.py`, with the fake-based unit tests.
6. `report_session`, schemas, router and mount; resolve the two UNVERIFIED points of §3.5;
   boundary and OpenAPI tests (§6.3); regenerate `openapi.json`.
7. Integration scenarios R1-R15, recent purchases, STL sales, top rated, customers, overview,
   no-PII (§6.2).
8. The measurement of §4.2 at 100k rows. Only if M1 or M3 is over 50 ms p95: the index revision
   (`down_revision = "eeed201dcfd2"`), its parity `Index(...)` and an upgrade/downgrade test.
9. Docs of §7 (ADR-045, ADR-024 strike-through, SRS, slice plan, VS-030 plan, handoff).

**CP1 (owner sign-off, after step 9):**
- pass counts for unit, integration, boundary matrix and architecture;
- the R9 / R9b / R9c / R10 figures as a table, and the `is_paid_line` mutation result;
- the M1-M7 table with p50 and p95, and the migration decision it led to;
- `alembic heads` = one head (`eeed201dcfd2`, or the new index revision);
- the `openapi.json` diff;
- one sample `/revenue` body for the seeded R1-R11 data.

---

## 9. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | Restated periods (D4) confuse whoever compares last month's screenshot with today's | ADR-045 and §27.1 say so plainly; Q2 offers the alternative |
| R2 | A 366-day revenue range loads every paid line into memory | Chunked reads (5,000), integers only. M7 measures the route at 100k payments (~200k lines). Over 2 s p95 goes to the owner. |
| R3 | `zoneinfo` finds no `Asia/Beirut` in a slim image or on Windows | `tzdata` becomes a dependency (step 2). A unit test constructs the zone. |
| R4 | The refund rules drift between Payments' domain and the reporting SQL | R16's parity matrix over every `(kind, status, reissued)`. The predicates sit next to each other in Payments, never in reporting. |
| R5 | `report_session` uses a second pooled connection per analytics request | 30/min per admin and a 5 s timeout bound it. One or a few admins. |
| R6 | A timeout surfaces as 500 rather than 503 | Resolved in step 6 (§3.5, UNVERIFIED). Either way an error, never zeros (R13). |
| R7 | Heavy reports load the primary database | The read-only snapshot, the timeout and the limit. No replica in V1. |
| R8 | Product names change after sale | STL sales uses today's label and falls back to the snapshot; recent purchases shows no names. |
| R9 | `postgresql_readonly` is not honoured by the dialect | R14 asserts the INSERT fails. The fallback is `SET TRANSACTION READ ONLY` first. |

---

## 10. Owner questions

**Answered 2026-10-27:** Q1-Q12 all **as recommended** (the chargeback-cancelled line stays
paid and nets to 0; dated by the payment; pending refunds count; a new `reporting` context;
the partial index only if CP1 > 50 ms p95; 400 `INVALID_DATE_RANGE`; reads unaudited, no PII;
30/min and 5 s; `min_reviews` 3; ADR-045; §5.7 customer statistics; excess shown apart).

1. **A line cancelled by a chargeback stays a paid line and its chargeback nets it to 0, so
   the exclusion side drops (D3)?**
   *Recommendation:* yes.
   - It is L2's own "bare cancel" rule (`domain/refunds.py:198`), so balances and revenue
     cannot disagree.
   - The chargeback is subtracted exactly once, whatever order cancel and chargeback come in
     (R9, R9b, R10).
   - Gross still shows that the sale happened.
2. **Refunds and chargebacks dated by their payment's date, so past periods restate?**
   *Recommendation:* yes, as the slice says (`vertical-slice-plan.md:1189`). Each line's
   figure is complete in one bucket. Dating refunds by their own date would need a second
   "refunds in period" series and could make a period negative. That could come later as a
   separate figure, not in V1.
3. **Pending refunds already reduce revenue (VS-030 plan §3.7)?**
   *Recommendation:* yes. A pending refund is money the business has decided to return. A
   failed one stops counting until it is reissued.
4. **A new `reporting` context, rather than Engagement (which hosts wishlist/funnel) or
   Fulfillment?**
   *Recommendation:* new.
   - Revenue is not engagement, and Fulfillment runs order operations.
   - A context of its own gets the architecture rules (D7) and keeps reads out of operational
     code.
   - The existing wishlist and funnel routes stay where they are.
5. **The index, only if M1 or M3 is over 50 ms p95, as a partial `(verified_at DESC, id DESC)
   WHERE status IN (paid, partially_refunded, refunded)` rather than `(status, verified_at)`?**
   *Recommendation:* yes (§4.2). One index serves both the range and the ordered page, and the
   partial predicate keeps it small and off the failed and expired rows.
6. **Range errors 400 `INVALID_DATE_RANGE`; `from`/`to` as inclusive Beirut dates, default the
   last 30 days, at most 366; the funnel's 422 left as a follow-up?**
   *Recommendation:* yes (D6). The slice and api-endpoints both say 400 (`:1198`, `:691-696`).
   A date is what a dashboard picks. Changing the funnel is a contract change of its own.
7. **Analytics reads not audited, and no PII in any response?**
   *Recommendation:* yes. Only figures and opaque `user_id`s are shown, and the admin order
   queue's reads are not audited either. BR-132 audits actions; these are reads.
8. **A 30/min per-admin analytics limit and a 5 s statement timeout?**
   *Recommendation:* yes. The 300/min admin limit is sized for queue work. A year-long report
   is heavier, and the timeout keeps a slow one from holding a connection.
9. **Top rated: `min_reviews` default 3, hidden-but-live products included and flagged,
   deleted ones excluded?**
   *Recommendation:* yes. A single five-star review should not top the list by default, and
   the admin may lower it to 1. Hidden products follow the wishlist precedent
   (`product_repository.py:145-146`).
10. **ADR-045, not an append to ADR-042 or ADR-024?**
    *Recommendation:* ADR-045. This slice adds a context, a session mode and the revenue
    definition: new mechanism, not a completion of an existing one (unlike VS-037 → ADR-044).
11. **Customer statistics as §5.7 (registered now; new, buyers and repeat buyers in range; net
    per buyer)?**
    *Recommendation:* yes. Each number comes from one context, and none needs the full
    purchase history. "First-time buyers" would need a scan of every past order and is left
    out of V1.
12. **A chargeback's excess shown as `unattributed_chargeback_excess_cents` and not subtracted
    from revenue?**
    *Recommendation:* yes. The slice note says excess "is not attributed to lines"
    (`vertical-slice-plan.md:1183`). Showing it keeps the bank's loss visible without
    corrupting the per-stream split.
