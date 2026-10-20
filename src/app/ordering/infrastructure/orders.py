"""`SqlOrderStore` (VS-023 plan 3.2). It never commits. Inserts that can lose a unique
race run in a SAVEPOINT, so the caller's transaction (and its cart lock) survives."""

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, insert, select, tuple_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import OrderItemStatus, OrderStatus, PaymentMethod
from app.ordering.domain.exceptions import OrderNumberExhaustedError, ProductAlreadyOwnedError
from app.ordering.domain.orders import NewOrder, NewOrderLine, Order, OrderLine, StatusChange
from app.ordering.infrastructure.models import (
    OrderItemModel,
    OrderModel,
    OrderStatusHistoryModel,
)

ORDER_NUMBER_ATTEMPTS = 5
ORDER_NUMBER_INDEX = "uq_orders_order_number"
STL_OWNERSHIP_INDEX = "uq_order_items_stl_ownership"
OFFER_ONCE_INDEX = "uq_order_items_offer_once"
OWNED_STATES = (OrderItemStatus.AWAITING_DELIVERY, OrderItemStatus.DELIVERED)
LIVE_STL_STATES = (OrderItemStatus.PENDING, *OWNED_STATES)

_O, _I = OrderModel, OrderItemModel
_ORDER_COLUMNS = (
    _O.id,
    _O.order_number,
    _O.user_id,
    _O.customer_email_snapshot,
    _O.source,
    _O.status,
    _O.fulfillment_method,
    _O.payment_method,
    _O.subtotal_cents,
    _O.tax_cents,
    _O.total_cents,
    _O.currency,
    _O.placed_at,
    _O.cancelled_at,
)
_LINE_COLUMNS = (
    _I.id,
    _I.order_id,
    _I.user_id,
    _I.product_id,
    _I.product_type,
    _I.product_name_snapshot,
    _I.unit_price_cents,
    _I.quantity,
    _I.line_total_cents,
    _I.currency,
    _I.fulfillment_status,
    _I.offer_id,
)


def _constraint(error: IntegrityError) -> str | None:
    """The driver's own constraint name (the catalogue repositories' approach)."""
    name = getattr(getattr(error.orig, "__cause__", None), "constraint_name", None)
    return name if isinstance(name, str) else None


def _order(row: Any) -> Order:
    return Order(**{column.key: getattr(row, column.key) for column in _ORDER_COLUMNS})


def _line(row: Any) -> OrderLine:
    return OrderLine(**{column.key: getattr(row, column.key) for column in _LINE_COLUMNS})


class SqlOrderStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_order(self, order: NewOrder, number: Callable[[], str]) -> Order:
        values = {k: v for k, v in vars(order).items() if k != "order_number"}
        for _ in range(ORDER_NUMBER_ATTEMPTS):
            try:
                async with self._session.begin_nested():
                    row = (
                        await self._session.execute(
                            insert(_O)
                            .values(order_number=number(), **values)
                            .returning(*_ORDER_COLUMNS)
                        )
                    ).one()
                return _order(row)
            except IntegrityError as exc:
                if _constraint(exc) != ORDER_NUMBER_INDEX:
                    raise
        raise OrderNumberExhaustedError(f"{ORDER_NUMBER_ATTEMPTS} order numbers collided.")

    async def insert_lines(
        self, order: Order, lines: Sequence[NewOrderLine], *, status: OrderItemStatus
    ) -> list[OrderLine]:
        rows = [
            {
                **vars(line),
                "order_id": order.id,
                "user_id": order.user_id,
                "payment_method": order.payment_method,
                "fulfillment_status": status,
            }
            for line in lines
        ]
        try:
            async with self._session.begin_nested():
                result = await self._session.execute(
                    insert(_I).returning(*_LINE_COLUMNS, sort_by_parameter_order=True), rows
                )
                return [_line(row) for row in result.all()]
        except IntegrityError as exc:
            violated = _constraint(exc)
            if violated not in (STL_OWNERSHIP_INDEX, OFFER_ONCE_INDEX):
                raise
        stl = [line.product_id for line in lines if line.product_type is ProductType.STL]
        held = await self._live_stl_product_ids(order.user_id, stl)
        if violated == OFFER_ONCE_INDEX:
            # The offer's earlier line may be refunded, so no longer live: name it anyway.
            held |= {line.product_id for line in lines if line.offer_id is not None}
        raise ProductAlreadyOwnedError(tuple(sorted(held, key=str)))

    async def add_history(self, changes: Sequence[StatusChange]) -> None:
        if changes:
            await self._session.execute(
                insert(OrderStatusHistoryModel), [vars(change) for change in changes]
            )

    async def owned_stl_product_ids(self, user_id: UUID, product_ids: Sequence[UUID]) -> set[UUID]:
        return await self._stl_product_ids(user_id, product_ids, OWNED_STATES)

    async def _live_stl_product_ids(self, user_id: UUID, product_ids: Sequence[UUID]) -> set[UUID]:
        return await self._stl_product_ids(user_id, product_ids, LIVE_STL_STATES)

    async def _stl_product_ids(
        self, user_id: UUID, product_ids: Sequence[UUID], states: Sequence[OrderItemStatus]
    ) -> set[UUID]:
        if not product_ids:
            return set()
        result = await self._session.scalars(
            select(_I.product_id).where(
                _I.user_id == user_id,
                _I.product_type == ProductType.STL,
                _I.product_id.in_(product_ids),
                _I.fulfillment_status.in_(states),
            )
        )
        return set(result.all())

    async def order_number(self, order_id: UUID) -> str | None:
        number: str | None = await self._session.scalar(
            select(_O.order_number).where(_O.id == order_id)
        )
        return number

    async def unpaid_offer_order(self, offer_id: UUID) -> UUID | None:
        order_id: UUID | None = await self._session.scalar(
            select(_I.order_id)
            .join(_O, _O.id == _I.order_id)
            .where(
                _I.offer_id == offer_id,
                _I.fulfillment_status == OrderItemStatus.PENDING,
                _O.cancelled_at.is_(None),
            )
        )
        return order_id

    async def lock_order(self, order_id: UUID) -> Order | None:
        row = (
            await self._session.execute(
                select(*_ORDER_COLUMNS).where(_O.id == order_id).with_for_update()
            )
        ).first()
        return _order(row) if row is not None else None

    async def lock_lines(self, order_id: UUID) -> list[OrderLine]:
        # Redundant today: every writer of existing lines already holds the orders lock
        # (test_order_item_writers.py). Kept, per ADR-024 d9, for the future writers in
        # VS-023b, VS-024, VS-028 and VS-030.
        result = await self._session.execute(
            select(*_LINE_COLUMNS).where(_I.order_id == order_id).order_by(_I.id).with_for_update()
        )
        return [_line(row) for row in result.all()]

    async def lock_owned_order(self, order_id: UUID, user_id: UUID) -> Order | None:
        """The retry's lock: `orders` FOR UPDATE with the ownership predicate (VS-024 3.4)."""
        row = (
            await self._session.execute(
                select(*_ORDER_COLUMNS)
                .where(_O.id == order_id, _O.user_id == user_id)
                .with_for_update()
            )
        ).first()
        return _order(row) if row is not None else None

    async def orders_by_id(self, order_ids: Sequence[UUID]) -> dict[UUID, Order]:
        """Unlocked; the admin payment reads (VS-024 2.2)."""
        if not order_ids:
            return {}
        rows = await self._session.execute(select(*_ORDER_COLUMNS).where(_O.id.in_(order_ids)))
        return {row.id: _order(row) for row in rows}

    async def order_lines(self, order_id: UUID) -> list[OrderLine]:
        result = await self._session.execute(
            select(*_LINE_COLUMNS).where(_I.order_id == order_id).order_by(_I.id)
        )
        return [_line(row) for row in result.all()]

    async def set_line_status(
        self,
        line_ids: Sequence[UUID],
        status: OrderItemStatus,
        *,
        at: datetime,
        cancelled_at: datetime | None = None,
    ) -> None:
        if line_ids:
            values: dict[str, Any] = {"fulfillment_status": status, "updated_at": at}
            if cancelled_at is not None:
                values["cancelled_at"] = cancelled_at
            await self._session.execute(update(_I).where(_I.id.in_(line_ids)).values(**values))

    async def set_cancelled(self, order_id: UUID, *, at: datetime) -> None:
        """The first writer of `orders.cancelled_at`; only under the orders lock."""
        await self._session.execute(
            update(_O)
            .where(_O.id == order_id, _O.cancelled_at.is_(None))
            .values(cancelled_at=at, updated_at=at)
        )

    async def release_candidates(
        self, *, placed_before: datetime, after: tuple[datetime, UUID] | None, limit: int
    ) -> list[tuple[datetime, UUID]]:
        """Unpaid online orders placed at or before `placed_before`, keyset-paged by
        `(placed_at, id)` (`ix_orders_status_placed`). No lock."""
        query = release_candidates_query(placed_before=placed_before, after=after, limit=limit)
        return [(row.placed_at, row.id) for row in await self._session.execute(query)]

    async def set_order_status(self, order_id: UUID, status: OrderStatus, *, at: datetime) -> None:
        await self._session.execute(
            update(_O).where(_O.id == order_id).values(status=status, updated_at=at)
        )


def release_candidates_query(
    *, placed_before: datetime, after: tuple[datetime, UUID] | None, limit: int
) -> Select[datetime, UUID]:
    """The release job's selection, also EXPLAINed by its test (plan 6.2)."""
    query = select(_O.placed_at, _O.id).where(
        _O.status == OrderStatus.PENDING_PAYMENT,
        _O.payment_method == PaymentMethod.ONLINE,
        _O.placed_at <= placed_before,
    )
    if after is not None:
        query = query.where(tuple_(_O.placed_at, _O.id) > after)
    return query.order_by(_O.placed_at, _O.id).limit(limit)
