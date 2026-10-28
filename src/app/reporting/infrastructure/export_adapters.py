"""VS-044's adapters (ADR-046): each reads its context's `public` export function on the
export's read-only snapshot and copies only the fields the export records name."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.public import product_labels
from app.engagement.public import contact_messages_for_export, reviews_for_export
from app.identity.public import Address, addresses_for_export
from app.negotiation.public import ExportOfferRow, offers_for_export
from app.ordering.public import ExportOrderRow, FulfillmentMethod, orders_for_export, payment_due
from app.payments.public import customer_refunds, order_payment_reader
from app.reporting.application.ports import ExportSources
from app.reporting.domain.data_export import (
    ExportAddress,
    ExportContactMessage,
    ExportDeliveryAddress,
    ExportOffer,
    ExportOfferRound,
    ExportOrder,
    ExportOrderLine,
    ExportPayment,
    ExportRefund,
    ExportReview,
    ExportStatusChange,
    Money,
    money,
)


async def _names(session: AsyncSession, product_ids: Sequence[UUID]) -> dict[UUID, str]:
    found = await product_labels(session, list(set(product_ids)))
    return {pid: row.name for pid, row in found.items()}


def _address(a: Address) -> ExportAddress:
    d = a.details
    return ExportAddress(
        id=a.id,
        label=d.label,
        recipient_name=d.recipient_name,
        phone=d.phone,
        governorate=str(d.governorate),
        city=d.city,
        area=d.area,
        street=d.street,
        landmark_notes=d.landmark_notes,
        is_default=a.is_default,
        created_at=a.created_at,
        updated_at=a.updated_at,
        deleted=a.deleted_at is not None,
        deleted_at=a.deleted_at,
    )


class SqlExportAddresses:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def all(self, user_id: UUID) -> list[ExportAddress]:
        return [_address(a) for a in await addresses_for_export(self._session, user_id)]


class SqlExportOrders:
    """The VS-025 projection: the shown attempt (provider, status, amount) and the customer's
    refunds (VS-030 Q9); never a provider reference, an actor or a reason."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def page(
        self, user_id: UUID, *, after: tuple[datetime, UUID] | None, limit: int
    ) -> list[ExportOrder]:
        rows = await orders_for_export(self._session, user_id, after=after, limit=limit)
        views = await order_payment_reader(self._session).views([r.order.id for r in rows])
        found = []
        for row in rows:
            view = views.get(row.order.id)
            refunds = await customer_refunds(self._session, row.order.id)
            reached_paid = view.reached_paid if view is not None else False
            shown = view.shown if view is not None else None
            payment = (
                ExportPayment(
                    shown.provider, shown.status, Money(shown.amount_cents, shown.currency)
                )
                if shown is not None
                else None
            )
            found.append(
                _order(
                    row,
                    reached_paid=reached_paid,
                    payment=payment,
                    refunds=[
                        ExportRefund(
                            str(r.kind), r.status, Money(r.amount_cents, r.currency), r.created_at
                        )
                        for r in refunds
                    ],
                )
            )
        return found


def _order(
    row: ExportOrderRow,
    *,
    reached_paid: bool,
    payment: ExportPayment | None,
    refunds: list[ExportRefund],
) -> ExportOrder:
    o, c = row.order, row.order.currency
    due = payment_due(status=o.status, payment_method=o.payment_method, reached_paid=reached_paid)
    delivery = o.fulfillment_method is FulfillmentMethod.DELIVERY
    return ExportOrder(
        id=o.id,
        order_number=o.order_number,
        source=str(o.source),
        status=str(o.status),
        payment_method=str(o.payment_method),
        fulfillment_method=str(o.fulfillment_method) if o.fulfillment_method else None,
        payment_due=due,
        amount_due=Money(int(o.live_total_cents), c) if due else None,  # SUM is NUMERIC
        subtotal=Money(o.subtotal_cents, c),
        tax=Money(o.tax_cents, c),
        total=Money(o.total_cents, c),
        delivery_address=ExportDeliveryAddress(
            o.recipient_name, o.governorate, o.city, o.area, o.street, o.landmark_notes
        )
        if delivery
        else None,
        contact_phone=o.contact_phone_snapshot,
        delivery_email=row.delivery_email,
        customer_note=o.customer_note,
        estimated_dispatch_at=o.estimated_dispatch_at,
        placed_at=o.placed_at,
        completed_at=o.completed_at,
        cancelled_at=o.cancelled_at,
        lines=[
            ExportOrderLine(
                id=line.id,
                product_id=line.product_id,
                product_type=str(line.product_type),
                name=line.product_name_snapshot,
                offer_id=line.offer_id,
                unit_price=Money(line.unit_price_cents, line.currency),
                quantity=line.quantity,
                line_total=Money(line.line_total_cents, line.currency),
                fulfillment_status=str(line.fulfillment_status),
                fulfilled_at=line.fulfilled_at,
                cancelled_at=line.cancelled_at,
                receipt_confirmed_at=line.receipt_confirmed_at,
                problem_reported_at=line.problem_reported_at,
            )
            for line in row.lines
        ],
        payment=payment,
        refunds=refunds,
        status_history=[
            ExportStatusChange(h.order_item_id, h.from_status, h.to_status, h.created_at)
            for h in row.history
        ],
    )


class SqlExportReviews:
    """`reviews_for_export` masks the badge of a WhatsApp-only product (VS-036 D14)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def all(self, user_id: UUID) -> list[ExportReview]:
        rows = await reviews_for_export(self._session, user_id)
        names = await _names(self._session, [r.product_id for r in rows])
        return [
            ExportReview(
                id=r.id,
                product_id=r.product_id,
                product_name=names.get(r.product_id),
                rating=r.rating,
                body=r.body,
                is_verified_purchase=r.is_verified_purchase,
                is_hidden=r.is_hidden,
                created_at=r.created_at,
                updated_at=r.updated_at,
                deleted=r.deleted_at is not None,
                deleted_at=r.deleted_at,
            )
            for r in rows
        ]


def _offer(row: ExportOfferRow, names: dict[UUID, str]) -> ExportOffer:
    o = row.offer
    return ExportOffer(
        id=o.id,
        product_id=o.product_id,
        product_name=names.get(o.product_id),
        status=str(o.status),
        turn=str(o.turn) if o.turn else None,
        initial_amount=Money(o.initial_amount_cents, o.currency),
        current_amount=Money(o.current_amount_cents, o.currency),
        agreed_amount=money(o.agreed_amount_cents, o.currency),
        responds_by=o.responds_by,
        accepted_at=o.accepted_at,
        checkout_expires_at=o.checkout_expires_at,
        cooldown_until=o.cooldown_until,
        created_at=o.created_at,
        updated_at=o.updated_at,
        rounds=[
            ExportOfferRound(
                r.sequence,
                str(r.actor),
                str(r.action),
                money(r.amount_cents, r.currency),
                r.message,
                r.created_at,
            )
            for r in row.rounds
        ],
    )


class SqlExportOffers:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def all(self, user_id: UUID) -> list[ExportOffer]:
        rows = await offers_for_export(self._session, user_id)
        names = await _names(self._session, [r.offer.product_id for r in rows])
        return [_offer(row, names) for row in rows]


class SqlExportContactMessages:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def all(self, user_id: UUID) -> list[ExportContactMessage]:
        rows = await contact_messages_for_export(self._session, user_id)
        return [ExportContactMessage(r.subject, r.message, r.created_at) for r in rows]


def export_sources(session: AsyncSession) -> ExportSources:
    return ExportSources(
        addresses=SqlExportAddresses(session),
        orders=SqlExportOrders(session),
        reviews=SqlExportReviews(session),
        offers=SqlExportOffers(session),
        contact_messages=SqlExportContactMessages(session),
    )
