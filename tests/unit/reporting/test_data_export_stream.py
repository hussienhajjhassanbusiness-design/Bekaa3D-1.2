"""VS-044: the section pager and the streamed JSON writer, without a database."""

import json
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from app.reporting.api.data_export import export_head, json_chunks
from app.reporting.api.export_schemas import DataExportRead
from app.reporting.application.data_export import export_sections
from app.reporting.application.ports import ExportSources
from app.reporting.domain.data_export import (
    SECTIONS,
    ExportAddress,
    ExportContactMessage,
    ExportOffer,
    ExportOrder,
    ExportProfile,
    ExportReview,
    Money,
)

NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)
USER = uuid4()


def _order(i: int) -> ExportOrder:
    usd = Money(1000, "USD")
    return ExportOrder(
        id=uuid4(),
        order_number=f"B3D-{i}",
        source="cart",
        status="completed",
        payment_method="online",
        fulfillment_method=None,
        payment_due=False,
        amount_due=None,
        subtotal=usd,
        tax=Money(0, "USD"),
        total=usd,
        delivery_address=None,
        contact_phone=None,
        delivery_email="a@example.com",
        customer_note=None,
        estimated_dispatch_at=None,
        placed_at=NOW + timedelta(minutes=i),
        completed_at=None,
        cancelled_at=None,
        lines=[],
        payment=None,
        refunds=[],
        status_history=[],
    )


class _Orders:
    def __init__(self, orders: list[ExportOrder]) -> None:
        self.orders = orders
        self.calls: list[tuple[datetime, UUID] | None] = []

    async def page(
        self, user_id: UUID, *, after: tuple[datetime, UUID] | None, limit: int
    ) -> list[ExportOrder]:
        assert user_id == USER
        self.calls.append(after)
        start = (
            0
            if after is None
            else next(i + 1 for i, o in enumerate(self.orders) if (o.placed_at, o.id) == after)
        )
        return self.orders[start : start + limit]


class _Empty:
    async def all(self, user_id: UUID) -> list[Any]:
        assert user_id == USER
        return []


class _Messages:
    async def all(self, user_id: UUID) -> list[ExportContactMessage]:
        return [ExportContactMessage("Problem with order B3D-1", "It broke", NOW)]


def _sources(orders: _Orders) -> ExportSources:
    empty = _Empty()
    return ExportSources(
        addresses=empty,
        orders=orders,
        reviews=empty,
        offers=empty,
        contact_messages=_Messages(),
    )


async def _collect(it: AsyncIterator[tuple[str, Sequence[object]]]) -> list[tuple[str, int]]:
    return [(key, len(batch)) async for key, batch in it]


async def test_orders_are_paged_and_every_set_appears_once_in_order() -> None:
    orders = _Orders([_order(i) for i in range(5)])
    found = await _collect(export_sections(_sources(orders), USER, page_size=2))
    assert found == [
        ("addresses", 0),
        ("orders", 2),
        ("orders", 2),
        ("orders", 1),
        ("reviews", 0),
        ("offers", 0),
        ("contact_messages", 1),
    ]
    assert orders.calls[1] == (orders.orders[1].placed_at, orders.orders[1].id)


async def test_an_exact_page_multiple_ends_on_an_empty_page() -> None:
    orders = _Orders([_order(i) for i in range(4)])
    found = await _collect(export_sections(_sources(orders), USER, page_size=2))
    assert [n for key, n in found if key == "orders"] == [2, 2, 0]


def _profile() -> ExportProfile:
    return ExportProfile(USER, "a@example.com", "customer", True, NOW, NOW)


async def _document(orders: int, page_size: int) -> tuple[list[bytes], bytes]:
    sections = export_sections(
        _sources(_Orders([_order(i) for i in range(orders)])), USER, page_size=page_size
    )
    chunks = [c async for c in json_chunks(export_head(_profile(), NOW), sections)]
    return chunks, b"".join(chunks)


async def test_the_chunks_join_into_one_document_matching_the_schema() -> None:
    chunks, body = await _document(orders=5, page_size=2)
    assert len(chunks) > 3
    parsed = json.loads(body)
    assert list(parsed) == ["format_version", "exported_at", "profile", *SECTIONS]
    assert [o["order_number"] for o in parsed["orders"]] == [f"B3D-{i}" for i in range(5)]
    assert parsed["addresses"] == []
    DataExportRead.model_validate_json(body)


async def test_an_empty_history_is_still_a_complete_document() -> None:
    _, body = await _document(orders=0, page_size=2)
    parsed = DataExportRead.model_validate_json(body)
    assert parsed.orders == [] and parsed.profile.id == USER
    assert len(parsed.contact_messages) == 1


async def test_nothing_is_sent_before_the_first_read() -> None:
    """The head goes out with the first section, so a failed first read is a clean 503."""

    class _Failing:
        async def all(self, user_id: UUID) -> list[ExportAddress]:
            raise RuntimeError("down")

    sources = _sources(_Orders([]))
    broken = ExportSources(
        _Failing(), sources.orders, sources.reviews, sources.offers, sources.contact_messages
    )
    chunks = json_chunks(export_head(_profile(), NOW), export_sections(broken, USER))
    try:
        await anext(chunks)
    except RuntimeError:
        return
    raise AssertionError("a chunk was produced before the first read succeeded")


def test_review_and_offer_records_round_trip_through_the_schema() -> None:
    review = ExportReview(uuid4(), uuid4(), "Vase", 5, "Nice", True, False, NOW, NOW, True, NOW)
    offer = ExportOffer(
        uuid4(),
        uuid4(),
        None,
        "rejected",
        None,
        Money(500, "USD"),
        Money(500, "USD"),
        None,
        None,
        None,
        None,
        NOW,
        NOW,
        NOW,
        [],
    )
    doc = DataExportRead(
        format_version=1,
        exported_at=NOW,
        profile=_profile(),
        addresses=[],
        orders=[],
        reviews=[review],
        offers=[offer],
        contact_messages=[],
    )
    assert DataExportRead.model_validate_json(doc.model_dump_json()) == doc
