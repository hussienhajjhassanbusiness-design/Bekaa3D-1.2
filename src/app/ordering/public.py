"""Ordering's published surface for other contexts (frozen at VS-023 Checkpoint 2).

Every write here follows the ADR-024 lock order: the `orders` row first, then its lines
by id; a caller that also locks a payment does so only after `lock_order_for_change`."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.application.ports import ProductType
from app.ordering.domain.admin_orders import (
    AdminHistoryEntry,
    AdminOrder,
    AdminOrderFilters,
    AdminOrderLine,
    CashBlock,
    cash_due,
)
from app.ordering.domain.cash import amount_due_cents
from app.ordering.domain.customer_view import payment_due
from app.ordering.domain.enums import (
    CancelReason,
    FulfillmentMethod,
    OrderItemStatus,
    OrderSource,
    OrderStatus,
    PaymentMethod,
)
from app.ordering.domain.exceptions import (
    CashAmountMismatchError,
    HandoverRefusedError,
    InvalidLineTransitionError,
    LineNotFoundError,
    LiveAttemptExistsError,
    OfferCheckoutExpiredError,
    OfferCheckoutNotFoundError,
    OfferNotCheckoutableError,
    OrderNotReleasableError,
)
from app.ordering.domain.fulfillment import DELIVERY_FEE_NOTE
from app.ordering.domain.fulfillment_steps import step_reached
from app.ordering.domain.handover import (
    HANDED_OVER,
    HandoverRefusal,
    handover_amount_matches,
    handover_refusal,
)
from app.ordering.domain.line_transitions import (
    LineContext,
    TransitionRefusal,
    available_targets,
    line_transition_refusal,
)
from app.ordering.domain.order_status import (
    LineState,
    OrderStatusInputs,
    RefundFacts,
    derive_order_status,
)
from app.ordering.domain.orders import Order, OrderLine, StatusChange, StlDeliveryRow
from app.ordering.domain.payment_recovery import (
    ReleaseRefusal,
    can_retry_payment,
    hold_deadline,
    manual_release_available_at,
    manual_release_refusal,
)
from app.ordering.infrastructure.admin_orders import SqlAdminOrders
from app.ordering.infrastructure.cash import SqlCashBlockStore
from app.ordering.infrastructure.cash import lock_cash_phone as _lock_cash_phone
from app.ordering.infrastructure.orders import SqlOrderStore

__all__ = [
    "DELIVERY_FEE_NOTE",
    "AdminHistoryEntry",
    "AdminOrder",
    "AdminOrderFilters",
    "AdminOrderLine",
    "CancelReason",
    "CashAmountMismatchError",
    "CashBlock",
    "FulfillmentMethod",
    "HandoverRefusal",
    "HandoverRefusedError",
    "InvalidLineTransitionError",
    "LineContext",
    "LineNotFoundError",
    "LineState",
    "LiveAttemptExistsError",
    "LockedOrder",
    "OfferCheckoutExpiredError",
    "OfferCheckoutNotFoundError",
    "OfferNotCheckoutableError",
    "OrderItemStatus",
    "OrderLine",
    "OrderNotReleasableError",
    "OrderSource",
    "OrderStatus",
    "OrderStatusInputs",
    "PaymentMethod",
    "ReleaseRefusal",
    "SqlCashBlockStore",
    "StlDeliveryRow",
    "TransitionRefusal",
    "admin_order_page",
    "admin_orders",
    "amount_due_cents",
    "available_targets",
    "can_retry_payment",
    "cash_block_store",
    "cash_due",
    "check_cash_handover",
    "derive_order_status",
    "hand_over_cash_lines",
    "hold_deadline",
    "line_context",
    "lock_cash_phone",
    "lock_order_for_change",
    "manual_release_available_at",
    "manual_release_refusal",
    "mark_order_paid",
    "mark_stl_line_delivered",
    "order_lines",
    "orders_by_id",
    "payment_due",
    "recompute_order_status",
    "release_candidates",
    "release_unpaid_order",
    "status_inputs_for",
    "step_reached",
    "stl_delivery_page",
    "stl_owned",
    "transition_physical_line",
    "unpaid_offer_order",
]


@dataclass(frozen=True)
class LockedOrder:
    order: Order
    lines: tuple[OrderLine, ...]


async def lock_cash_phone(session: AsyncSession, phone_hash: str) -> None:
    """The cash phone advisory lock, the one checkout takes (VS-028 D6). Call it only after
    the customer's cart lock (ADR-024 d9); `test_cash_lock_order` allowlists the callers."""
    await _lock_cash_phone(session, phone_hash)


def cash_block_store(session: AsyncSession) -> SqlCashBlockStore:
    """VS-031 inserts blocks and VS-029 lists and clears them through this store."""
    return SqlCashBlockStore(session)


async def lock_order_for_change(session: AsyncSession, order_id: UUID) -> LockedOrder | None:
    """ADR-024 d9 steps 1-2: `orders` FOR UPDATE, then every line FOR UPDATE by id."""
    store = SqlOrderStore(session)
    order = await store.lock_order(order_id)
    if order is None:
        return None
    return LockedOrder(order=order, lines=tuple(await store.lock_lines(order_id)))


async def recompute_order_status(
    session: AsyncSession,
    locked: LockedOrder,
    inputs: OrderStatusInputs,
    *,
    actor_user_id: UUID | None = None,
    reason: str | None = None,
) -> OrderStatus:
    """The only writer of `orders.status`; a history row only when it changes."""
    status = derive_order_status(inputs)
    if status is not locked.order.status:
        at = datetime.now(UTC)
        store = SqlOrderStore(session)
        await store.set_order_status(locked.order.id, status, at=at)
        await store.add_history(
            [
                StatusChange(
                    locked.order.id,
                    locked.order.status.value,
                    status.value,
                    actor_user_id=actor_user_id,
                    reason=reason,
                )
            ]
        )
    return status


async def mark_order_paid(session: AsyncSession, locked: LockedOrder, *, at: datetime) -> None:
    """Payment verified: STL lines `pending -> awaiting_delivery` (ADR-019 d2), physical
    lines stay `pending`; history rows, then the recomputed status. Caller holds the locks."""
    store = SqlOrderStore(session)
    stl = [
        line
        for line in locked.lines
        if line.product_type is ProductType.STL
        and line.fulfillment_status is OrderItemStatus.PENDING
    ]
    await store.set_line_status([line.id for line in stl], OrderItemStatus.AWAITING_DELIVERY, at=at)
    await store.add_history(
        [
            StatusChange(
                locked.order.id,
                OrderItemStatus.PENDING.value,
                OrderItemStatus.AWAITING_DELIVERY.value,
                order_item_id=line.id,
            )
            for line in stl
        ]
    )
    moved = {line.id for line in stl}
    states = tuple(
        LineState(
            OrderItemStatus.AWAITING_DELIVERY if line.id in moved else line.fulfillment_status
        )
        for line in locked.lines
    )
    await recompute_order_status(
        session,
        locked,
        OrderStatusInputs(
            payment_method=locked.order.payment_method,
            cancelled_at_set=locked.order.cancelled_at is not None,
            payment_reached_paid=True,
            lines=states,
        ),
    )


def status_inputs_for(
    locked: LockedOrder, lines: tuple[LineState, ...], *, reached_paid: bool
) -> OrderStatusInputs:
    """STOP-GAP: VS-030 must replace `refund_present` with the real refund query; until
    then a `partially_refunded` order keeps that status."""
    return OrderStatusInputs(
        payment_method=locked.order.payment_method,
        cancelled_at_set=locked.order.cancelled_at is not None,
        payment_reached_paid=reached_paid,
        lines=lines,
        refunds=RefundFacts(
            present=reached_paid and locked.order.status is OrderStatus.PARTIALLY_REFUNDED
        ),
    )


def _line(locked: LockedOrder, line_id: UUID) -> OrderLine:
    line = next((item for item in locked.lines if item.id == line_id), None)
    if line is None:
        raise LineNotFoundError(f"line {line_id} is not on order {locked.order.id}")
    return line


def line_context(locked: LockedOrder, line: OrderLine, *, reached_paid: bool) -> LineContext:
    order = locked.order
    return LineContext(
        line.product_type, order.fulfillment_method, order.payment_method, reached_paid
    )


async def mark_stl_line_delivered(
    session: AsyncSession, locked: LockedOrder, *, line_id: UUID, admin_id: UUID, at: datetime
) -> tuple[OrderLine, OrderStatus]:
    """Admin sent the file: STL `awaiting_delivery -> delivered`, history, recomputed status.
    The caller holds the orders and lines locks; the state is read from `locked`."""
    line = _line(locked, line_id)
    refusal = line_transition_refusal(
        line_context(locked, line, reached_paid=True),
        line.fulfillment_status,
        OrderItemStatus.DELIVERED,
    )
    if refusal is not None:
        raise InvalidLineTransitionError(refusal.value, fulfilled_at=line.fulfilled_at)
    store = SqlOrderStore(session)
    if not await store.set_line_delivered(line_id, at=at, delivered_by=admin_id):
        raise InvalidLineTransitionError("not_awaiting_delivery")
    await store.add_history(
        [
            StatusChange(
                locked.order.id,
                OrderItemStatus.AWAITING_DELIVERY.value,
                OrderItemStatus.DELIVERED.value,
                order_item_id=line_id,
                actor_user_id=admin_id,
            )
        ]
    )
    states = tuple(
        LineState(OrderItemStatus.DELIVERED if item.id == line_id else item.fulfillment_status)
        for item in locked.lines
    )
    order_status = await recompute_order_status(
        session,
        locked,
        status_inputs_for(locked, states, reached_paid=True),
        actor_user_id=admin_id,
    )
    delivered = replace(
        line,
        fulfillment_status=OrderItemStatus.DELIVERED,
        fulfilled_at=at,
        delivered_by=admin_id,
    )
    return delivered, order_status


async def transition_physical_line(
    session: AsyncSession,
    locked: LockedOrder,
    *,
    line_id: UUID,
    target: OrderItemStatus,
    admin_id: UUID,
    at: datetime,
    reached_paid: bool,
    note: str | None,
) -> tuple[OrderLine, OrderStatus]:
    """A physical forward edge (VS-029), decided on the state in `locked`; history, then
    the recomputed status. `reached_paid` is read after the caller took the locks."""
    line = _line(locked, line_id)
    current = line.fulfillment_status
    refusal = line_transition_refusal(
        line_context(locked, line, reached_paid=reached_paid), current, target
    )
    if line.product_type is not ProductType.PHYSICAL:
        refusal = refusal or TransitionRefusal.NOT_A_LEGAL_EDGE
    if refusal is not None:
        raise InvalidLineTransitionError(
            refusal.value, fulfilled_at=line.fulfilled_at, current_status=current.value
        )
    store = SqlOrderStore(session)
    if not await store.move_line(line_id, from_status=current, to_status=target, at=at):
        raise InvalidLineTransitionError(
            TransitionRefusal.NOT_A_LEGAL_EDGE.value, current_status=current.value
        )
    await store.add_history(
        [
            StatusChange(
                locked.order.id,
                current.value,
                target.value,
                order_item_id=line_id,
                actor_user_id=admin_id,
                reason=note,
            )
        ]
    )
    states = tuple(
        LineState(target if item.id == line_id else item.fulfillment_status)
        for item in locked.lines
    )
    order_status = await recompute_order_status(
        session,
        locked,
        status_inputs_for(locked, states, reached_paid=reached_paid),
        actor_user_id=admin_id,
    )
    return replace(line, fulfillment_status=target), order_status


def check_cash_handover(locked: LockedOrder, *, typed_cents: int, typed_currency: str) -> int:
    """SRS 9.8.3 under the locks: the 409 reasons first, then the amount (422). Returns
    the amount due, `amount_due_cents` over the locked lines (ADR-033)."""
    order = locked.order
    states = [line.fulfillment_status for line in locked.lines]
    refusal = handover_refusal(order.payment_method, order.fulfillment_method, states)
    if refusal is not None:
        raise HandoverRefusedError(refusal.value)
    due = amount_due_cents(locked.lines)
    if typed_currency != order.currency or not handover_amount_matches(
        due_cents=due, typed_cents=typed_cents
    ):
        raise CashAmountMismatchError(due, order.currency)
    return due


async def hand_over_cash_lines(
    session: AsyncSession, locked: LockedOrder, *, admin_id: UUID, at: datetime, note: str | None
) -> tuple[tuple[OrderLine, ...], OrderStatus]:
    """Every live line delivered / picked up, history, the status recomputed as paid.
    Only after `check_cash_handover` and the cash payment's INSERT, under the same locks."""
    order = locked.order
    method = order.fulfillment_method
    states = [line.fulfillment_status for line in locked.lines]
    refusal = handover_refusal(order.payment_method, method, states)
    if refusal is not None or method is None:
        raise HandoverRefusedError((refusal or HandoverRefusal.NOT_A_CASH_ORDER).value)
    done = HANDED_OVER[method]
    store = SqlOrderStore(session)
    live = [
        line for line in locked.lines if line.fulfillment_status is not OrderItemStatus.CANCELLED
    ]
    for line in live:
        moved = await store.move_line(
            line.id, from_status=line.fulfillment_status, to_status=done, at=at
        )
        if not moved:
            raise HandoverRefusedError(HandoverRefusal.LINES_NOT_READY.value)
    await store.add_history(
        [
            StatusChange(
                order.id,
                line.fulfillment_status.value,
                done.value,
                order_item_id=line.id,
                actor_user_id=admin_id,
                reason=note,
            )
            for line in live
        ]
    )
    ids = {line.id for line in live}
    after = tuple(
        LineState(done if line.id in ids else line.fulfillment_status) for line in locked.lines
    )
    order_status = await recompute_order_status(
        session, locked, status_inputs_for(locked, after, reached_paid=True), actor_user_id=admin_id
    )
    return tuple(replace(line, fulfillment_status=done) for line in live), order_status


def admin_orders(session: AsyncSession) -> SqlAdminOrders:
    """The administrator's order reads and the internal note (VS-029). No lock."""
    return SqlAdminOrders(session)


async def admin_order_page(
    session: AsyncSession,
    filters: AdminOrderFilters,
    *,
    after: tuple[datetime, UUID] | None,
    limit: int,
) -> list[AdminOrder]:
    """The fulfillment queue, newest first; never an unpaid online order (BR-148)."""
    return await SqlAdminOrders(session).page(filters, after=after, limit=limit)


async def stl_delivery_page(
    session: AsyncSession,
    *,
    after: tuple[datetime, UUID] | None,
    limit: int,
    product_id: UUID | None = None,
    user_id: UUID | None = None,
) -> list[StlDeliveryRow]:
    """The admin delivery queue, oldest first. No lock."""
    return await SqlOrderStore(session).stl_delivery_page(
        after=after, limit=limit, product_id=product_id, user_id=user_id
    )


async def stl_owned(session: AsyncSession, *, user_id: UUID, product_id: UUID) -> bool:
    """A paid, unrefunded STL line (`awaiting_delivery` or `delivered`), ADR-019 d5."""
    return bool(await SqlOrderStore(session).owned_stl_product_ids(user_id, [product_id]))


async def release_unpaid_order(
    session: AsyncSession,
    locked: LockedOrder,
    *,
    at: datetime,
    reason: str,
    actor_user_id: UUID | None = None,
) -> tuple[UUID, ...]:
    """The hold release (VS-024 3.6): `cancelled_at`, pending lines cancelled, history,
    status `cancelled`. Caller holds orders, lines and payments; actor None is the job."""
    order = locked.order
    if (
        order.payment_method is not PaymentMethod.ONLINE
        or order.status is not OrderStatus.PENDING_PAYMENT
        or order.cancelled_at is not None
    ):
        raise OrderNotReleasableError(f"order {order.id} is not an unpaid online order")
    store = SqlOrderStore(session)
    await store.set_cancelled(order.id, at=at)
    ids = [line.id for line in locked.lines if line.fulfillment_status is OrderItemStatus.PENDING]
    await store.set_line_status(ids, OrderItemStatus.CANCELLED, at=at, cancelled_at=at)
    await store.add_history(
        [
            StatusChange(
                order.id,
                OrderItemStatus.PENDING.value,
                OrderItemStatus.CANCELLED.value,
                order_item_id=line_id,
                actor_user_id=actor_user_id,
                reason=reason,
            )
            for line_id in ids
        ]
    )
    states = tuple(
        LineState(OrderItemStatus.CANCELLED if line.id in ids else line.fulfillment_status)
        for line in locked.lines
    )
    await recompute_order_status(
        session,
        locked,
        OrderStatusInputs(
            payment_method=order.payment_method,
            cancelled_at_set=True,
            payment_reached_paid=False,
            lines=states,
        ),
        actor_user_id=actor_user_id,
        reason=reason,
    )
    return tuple(ids)


async def release_candidates(
    session: AsyncSession,
    *,
    placed_before: datetime,
    after: tuple[datetime, UUID] | None,
    limit: int,
) -> list[tuple[datetime, UUID]]:
    """The release job's unlocked page of `(placed_at, id)`; never FOR UPDATE (8.1)."""
    return await SqlOrderStore(session).release_candidates(
        placed_before=placed_before, after=after, limit=limit
    )


async def orders_by_id(session: AsyncSession, order_ids: list[UUID]) -> dict[UUID, Order]:
    """Orders by id, no lock (VS-024 admin payment reads)."""
    return await SqlOrderStore(session).orders_by_id(order_ids)


async def order_lines(session: AsyncSession, order_id: UUID) -> list[OrderLine]:
    """The order's lines by id, no lock (VS-024 admin payment detail)."""
    return await SqlOrderStore(session).order_lines(order_id)


async def unpaid_offer_order(session: AsyncSession, offer_id: UUID) -> UUID | None:
    """The uncancelled order whose line still awaits payment for this offer. No lock."""
    return await SqlOrderStore(session).unpaid_offer_order(offer_id)
