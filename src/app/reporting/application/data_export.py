"""VS-044: the export's data sets in body order, the orders a page at a time so a large history
streams without being held in memory (ADR-046)."""

from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Final
from uuid import UUID

from app.reporting.application.ports import ExportSources

ORDER_PAGE_SIZE: Final = 50


async def export_sections(
    sources: ExportSources, user_id: UUID, *, page_size: int = ORDER_PAGE_SIZE
) -> AsyncIterator[tuple[str, Sequence[object]]]:
    """Each data set at least once, even empty; `orders` once per page."""
    yield "addresses", await sources.addresses.all(user_id)
    after: tuple[datetime, UUID] | None = None
    while True:
        page = await sources.orders.page(user_id, after=after, limit=page_size)
        yield "orders", page
        if len(page) < page_size:
            break
        after = (page[-1].placed_at, page[-1].id)
    yield "reviews", await sources.reviews.all(user_id)
    yield "offers", await sources.offers.all(user_id)
    yield "contact_messages", await sources.contact_messages.all(user_id)
