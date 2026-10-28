"""One port per context the reports read (ADR-045 d4). Every adapter calls only that
context's `public` module; no port joins across contexts."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.reporting.domain.data_export import (
    ExportAddress,
    ExportContactMessage,
    ExportOffer,
    ExportOrder,
    ExportReview,
)
from app.reporting.domain.metrics import (
    CustomerCounts,
    OrderLabel,
    PaidPayment,
    PendingOffers,
    ProductLabel,
    RatedProduct,
    ReportLine,
)


class PaidPayments(Protocol):
    """Payments: the paid payments and what a chargeback charged beyond the lines."""

    async def between(self, lower: datetime, upper: datetime) -> list[PaidPayment]: ...

    async def page(
        self, *, before: tuple[datetime, UUID] | None, limit: int
    ) -> list[PaidPayment]: ...

    async def excess_cents(self, payment_ids: Sequence[UUID]) -> int: ...


class LineRefunds(Protocol):
    """Payments: VS-030 plan 3.7's per-line refund reads."""

    async def refunded_cents_by_line(self, line_ids: Sequence[UUID]) -> dict[UUID, int]: ...

    async def covered_lines(self, line_ids: Sequence[UUID]) -> frozenset[UUID]: ...


class OrderLines(Protocol):
    async def lines(self, order_ids: Sequence[UUID]) -> list[ReportLine]: ...

    async def labels(self, order_ids: Sequence[UUID]) -> dict[UUID, OrderLabel]: ...

    async def stl_awaiting_delivery(self) -> dict[UUID, int]: ...


class OfferCounts(Protocol):
    async def live_counts(self) -> PendingOffers: ...


class ProductCatalog(Protocol):
    async def top_rated(self, *, limit: int, min_reviews: int) -> list[RatedProduct]: ...

    async def labels(self, product_ids: Sequence[UUID]) -> dict[UUID, ProductLabel]: ...


class Customers(Protocol):
    async def counts(self, created_from: datetime, created_to: datetime) -> CustomerCounts: ...


@dataclass(frozen=True)
class Sources:
    """The six ports, all on one read-only snapshot (ADR-045 d5)."""

    payments: PaidPayments
    refunds: LineRefunds
    orders: OrderLines
    offers: OfferCounts
    products: ProductCatalog
    customers: Customers


class ExportAddresses(Protocol):
    async def all(self, user_id: UUID) -> list[ExportAddress]: ...


class ExportOrders(Protocol):
    async def page(
        self, user_id: UUID, *, after: tuple[datetime, UUID] | None, limit: int
    ) -> list[ExportOrder]: ...


class ExportReviews(Protocol):
    async def all(self, user_id: UUID) -> list[ExportReview]: ...


class ExportOffers(Protocol):
    async def all(self, user_id: UUID) -> list[ExportOffer]: ...


class ExportContactMessages(Protocol):
    async def all(self, user_id: UUID) -> list[ExportContactMessage]: ...


@dataclass(frozen=True)
class ExportSources:
    """VS-044: one port per data set, all on one read-only snapshot (ADR-046)."""

    addresses: ExportAddresses
    orders: ExportOrders
    reviews: ExportReviews
    offers: ExportOffers
    contact_messages: ExportContactMessages
