"""One adapter per port (ADR-045 d4). Each reads its context's `public` reporting functions on
the request's read-only session and maps the rows onto reporting types."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.public import product_labels, top_rated_products
from app.identity.public import customer_counts
from app.negotiation.public import live_offer_counts
from app.ordering.public import report_lines, report_orders, stl_awaiting_delivery_counts
from app.payments.public import (
    PaidPaymentRow,
    chargeback_excess_cents,
    paid_payment_page,
    paid_payments_between,
    refund_covered_lines,
    refunded_cents_by_line,
)
from app.reporting.application.ports import Sources
from app.reporting.domain.metrics import (
    CustomerCounts,
    OrderLabel,
    PaidPayment,
    PendingOffers,
    ProductLabel,
    RatedProduct,
    ReportLine,
    Stream,
)


def _paid(rows: Sequence[PaidPaymentRow]) -> list[PaidPayment]:
    return [PaidPayment(row.id, row.order_id, row.verified_at) for row in rows]


class SqlPaidPayments:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def between(self, lower: datetime, upper: datetime) -> list[PaidPayment]:
        return _paid(await paid_payments_between(self._session, lower, upper))

    async def page(self, *, before: tuple[datetime, UUID] | None, limit: int) -> list[PaidPayment]:
        return _paid(await paid_payment_page(self._session, before=before, limit=limit))

    async def excess_cents(self, payment_ids: Sequence[UUID]) -> int:
        return await chargeback_excess_cents(self._session, payment_ids)


class SqlLineRefunds:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def refunded_cents_by_line(self, line_ids: Sequence[UUID]) -> dict[UUID, int]:
        return await refunded_cents_by_line(self._session, line_ids)

    async def covered_lines(self, line_ids: Sequence[UUID]) -> frozenset[UUID]:
        return await refund_covered_lines(self._session, line_ids)


class SqlOrderLines:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lines(self, order_ids: Sequence[UUID]) -> list[ReportLine]:
        return [
            ReportLine(
                row.id,
                row.order_id,
                row.user_id,
                row.product_id,
                row.name_snapshot,
                Stream(row.product_type),
                row.status,
                row.quantity,
                row.line_total_cents,
            )
            for row in await report_lines(self._session, order_ids)
        ]

    async def labels(self, order_ids: Sequence[UUID]) -> dict[UUID, OrderLabel]:
        found = await report_orders(self._session, order_ids)
        return {
            oid: OrderLabel(row.order_number, row.payment_method, row.user_id)
            for oid, row in found.items()
        }

    async def stl_awaiting_delivery(self) -> dict[UUID, int]:
        return await stl_awaiting_delivery_counts(self._session)


class SqlOfferCounts:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def live_counts(self) -> PendingOffers:
        found = await live_offer_counts(self._session)
        return PendingOffers(found["awaiting_admin"], found["awaiting_customer"], found["accepted"])


class SqlProductCatalog:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def top_rated(self, *, limit: int, min_reviews: int) -> list[RatedProduct]:
        rows = await top_rated_products(self._session, limit=limit, min_reviews=min_reviews)
        return [
            RatedProduct(
                row.product_id,
                row.name,
                row.slug,
                row.type,
                row.average_rating,
                row.review_count,
                row.is_visible,
            )
            for row in rows
        ]

    async def labels(self, product_ids: Sequence[UUID]) -> dict[UUID, ProductLabel]:
        found = await product_labels(self._session, product_ids)
        return {pid: ProductLabel(row.name, row.slug) for pid, row in found.items()}


class SqlCustomers:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def counts(self, created_from: datetime, created_to: datetime) -> CustomerCounts:
        row = await customer_counts(self._session, created_from=created_from, created_to=created_to)
        return CustomerCounts(row.registered, row.new_in_range)


def sql_sources(session: AsyncSession) -> Sources:
    return Sources(
        payments=SqlPaidPayments(session),
        refunds=SqlLineRefunds(session),
        orders=SqlOrderLines(session),
        offers=SqlOfferCounts(session),
        products=SqlProductCatalog(session),
        customers=SqlCustomers(session),
    )
