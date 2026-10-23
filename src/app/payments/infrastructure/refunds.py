"""`refunds` and `refund_items` (VS-030 plan 3.0-3.4). Every read that feeds a money or
status decision runs after the caller holds the order's row lock, and checks it does:
every refund writer takes that lock first, so the rows cannot change under the reader."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.application.ports import NO_REFUNDS, RefundFacts
from app.payments.domain.enums import PaymentProvider, RefundKind, RefundStatus
from app.payments.domain.exceptions import OrderLockRequiredError
from app.payments.domain.outcome import REACHED_PAID
from app.payments.domain.refunds import ItemFact, NewRefund, PaymentFact, Refund, facts_for
from app.payments.infrastructure.models import PaymentModel, RefundItemModel, RefundModel

_P, _R, _I = PaymentModel, RefundModel, RefundItemModel
_COLUMNS = (
    _R.id,
    _R.order_id,
    _R.payment_id,
    _R.payment_provider,
    _R.kind,
    _R.status,
    _R.amount_cents,
    _R.currency,
    _R.reissued_at,
)

# xmax is this transaction after `FOR UPDATE`; xmin is, once this transaction updated it.
_HOLDS_ORDER_LOCK = text(
    "SELECT (xmax::text = pg_current_xact_id()::xid::text"
    " OR xmin::text = pg_current_xact_id()::xid::text) FROM orders WHERE id = :o"
)


async def require_order_lock(session: AsyncSession, order_id: UUID) -> None:
    """Refuse a refund-fact read made without `lock_order_for_change` in this transaction."""
    held = (await session.execute(_HOLDS_ORDER_LOCK, {"o": order_id})).scalar()
    if not held:
        raise OrderLockRequiredError(f"order {order_id} is not locked by this transaction")


async def _items(session: AsyncSession, refund_ids: list[UUID]) -> dict[UUID, list[ItemFact]]:
    by_refund: dict[UUID, list[ItemFact]] = defaultdict(list)
    if refund_ids:
        rows = await session.execute(
            select(_I.refund_id, _I.order_item_id, _I.amount_cents)
            .where(_I.refund_id.in_(refund_ids))
            .order_by(_I.refund_id, _I.order_item_id)
        )
        for row in rows:
            by_refund[row.refund_id].append(ItemFact(row.order_item_id, row.amount_cents))
    return by_refund


def _refund(row: Any, items: list[ItemFact]) -> Refund:
    return Refund(
        row.id,
        row.order_id,
        row.payment_id,
        row.payment_provider,
        row.kind,
        row.status,
        row.amount_cents,
        row.currency,
        row.reissued_at,
        tuple(items),
    )


class SqlRefundStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _one(self, refund_id: UUID, *, lock: bool) -> Refund | None:
        query = select(*_COLUMNS).where(_R.id == refund_id)
        row = (await self._session.execute(query.with_for_update() if lock else query)).first()
        if row is None:
            return None
        return _refund(row, (await _items(self._session, [row.id]))[row.id])

    async def get(self, refund_id: UUID) -> Refund | None:
        return await self._one(refund_id, lock=False)

    async def lock(self, refund_id: UUID) -> Refund | None:
        return await self._one(refund_id, lock=True)

    async def for_order(self, order_id: UUID) -> list[Refund]:
        await require_order_lock(self._session, order_id)
        rows = (
            await self._session.execute(
                select(*_COLUMNS).where(_R.order_id == order_id).order_by(_R.id)
            )
        ).all()
        items = await _items(self._session, [row.id for row in rows])
        return [_refund(row, items[row.id]) for row in rows]

    async def insert(self, new: NewRefund) -> UUID:
        refund_id: UUID = (
            await self._session.execute(
                insert(_R)
                .values(
                    order_id=new.order_id,
                    payment_id=new.payment_id,
                    payment_provider=new.provider,
                    kind=new.kind,
                    status=RefundStatus.PENDING,
                    amount_cents=new.amount_cents,
                    currency=new.currency,
                    reason=new.reason,
                    requested_by=new.requested_by,
                    approved_by=new.approved_by,
                    reissue_of_refund_id=new.reissue_of_refund_id,
                    initiated_at=new.initiated_at,
                )
                .returning(_R.id)
            )
        ).scalar_one()
        if new.items:
            await self._session.execute(
                insert(_I),
                [
                    {
                        "refund_id": refund_id,
                        "order_id": new.order_id,
                        "order_item_id": item.order_item_id,
                        "amount_cents": item.amount_cents,
                    }
                    for item in new.items
                ],
            )
        return refund_id

    async def _move(
        self, refund_id: UUID, sources: tuple[RefundStatus, ...], **values: Any
    ) -> bool:
        """The state guard: the UPDATE matches only a row still in one of `sources`."""
        result = await self._session.execute(
            update(_R)
            .where(_R.id == refund_id, _R.status.in_(sources))
            .values(**values)
            .returning(_R.id)
        )
        return result.first() is not None

    async def settle(
        self, refund_id: UUID, *, by: UUID, at: datetime, reference: str | None, note: str | None
    ) -> bool:
        return await self._move(
            refund_id,
            (RefundStatus.PENDING,),
            status=RefundStatus.SETTLED,
            settled_at=at,
            settled_by=by,
            settlement_reference=reference,
            settlement_note=note,
            updated_at=at,
        )

    async def fail(self, refund_id: UUID, *, by: UUID, at: datetime, reason: str) -> bool:
        return await self._move(
            refund_id,
            (RefundStatus.PENDING,),
            status=RefundStatus.FAILED,
            failed_at=at,
            failed_by=by,
            failure_reason=reason,
            updated_at=at,
        )

    async def void(self, refund_id: UUID, *, by: UUID, at: datetime, reason: str) -> bool:
        result = await self._session.execute(
            update(_R)
            .where(
                _R.id == refund_id,
                (_R.status == RefundStatus.PENDING)
                | ((_R.status == RefundStatus.FAILED) & _R.reissued_at.is_(None)),
            )
            .values(
                status=RefundStatus.VOIDED,
                voided_at=at,
                voided_by=by,
                void_reason=reason,
                updated_at=at,
            )
            .returning(_R.id)
        )
        return result.first() is not None

    async def mark_reissued(self, refund_id: UUID, *, at: datetime) -> bool:
        result = await self._session.execute(
            update(_R)
            .where(_R.id == refund_id, _R.status == RefundStatus.FAILED, _R.reissued_at.is_(None))
            .values(reissued_at=at, updated_at=at)
            .returning(_R.id)
        )
        return result.first() is not None


async def order_refund_facts(session: AsyncSession, order_id: UUID) -> RefundFacts:
    """`NO_REFUNDS` until a payment reached paid. The caller holds the order's lock (the
    check refuses otherwise). Chargebacks join here in PR C."""
    await require_order_lock(session, order_id)
    paid = (
        await session.execute(
            select(_P.id, _P.provider, _P.status, _P.amount_cents, _P.currency).where(
                _P.order_id == order_id, _P.status.in_(REACHED_PAID)
            )
        )
    ).first()
    if paid is None:
        return NO_REFUNDS
    rows = await session.execute(select(*_COLUMNS).where(_R.order_id == order_id).order_by(_R.id))
    refunds = [_refund(row, []).fact() for row in rows]
    return facts_for(
        PaymentFact(paid.id, paid.provider, paid.status, paid.amount_cents, paid.currency),
        refunds,
    )


# --- Reads for responses: no lock, never a phone, hash, address or provider reference ---


@dataclass(frozen=True)
class RefundItemRow:
    order_item_id: UUID
    product_name: str
    amount_cents: int


@dataclass(frozen=True)
class RefundRow:
    id: UUID
    order_id: UUID
    order_number: str
    customer_id: UUID
    payment_id: UUID
    payment_provider: PaymentProvider
    kind: RefundKind
    status: RefundStatus
    amount_cents: int
    currency: str
    reason: str
    requested_by: UUID | None
    approved_by: UUID | None
    reissue_of_refund_id: UUID | None
    reissued_by_refund_id: UUID | None
    reissued_at: datetime | None
    settled_at: datetime | None
    settled_by: UUID | None
    settlement_reference: str | None
    settlement_note: str | None
    failed_at: datetime | None
    failed_by: UUID | None
    failure_reason: str | None
    voided_at: datetime | None
    voided_by: UUID | None
    void_reason: str | None
    created_at: datetime
    items: tuple[RefundItemRow, ...]


@dataclass(frozen=True)
class RefundFilters:
    queue: bool = True
    statuses: tuple[RefundStatus, ...] = ()
    kinds: tuple[RefundKind, ...] = ()
    order_id: UUID | None = None
    customer_id: UUID | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None


_DETAIL = text(
    "SELECT r.id, r.order_id, o.order_number, o.user_id AS customer_id, r.payment_id,"
    " r.payment_provider, r.kind, r.status, r.amount_cents, r.currency, r.reason,"
    " r.requested_by, r.approved_by, r.reissue_of_refund_id,"
    " (SELECT n.id FROM refunds n WHERE n.reissue_of_refund_id = r.id) AS reissued_by_refund_id,"
    " r.reissued_at, r.settled_at, r.settled_by, r.settlement_reference, r.settlement_note,"
    " r.failed_at, r.failed_by, r.failure_reason, r.voided_at, r.voided_by, r.void_reason,"
    " r.created_at"
    " FROM refunds r JOIN orders o ON o.id = r.order_id"
)


async def _rows(session: AsyncSession, where: str, params: dict[str, Any]) -> list[RefundRow]:
    rows = (await session.execute(text(f"{_DETAIL.text} {where}"), params)).all()
    ids = [row.id for row in rows]
    names: dict[UUID, list[RefundItemRow]] = defaultdict(list)
    if ids:
        items = await session.execute(
            text(
                "SELECT ri.refund_id, ri.order_item_id, oi.product_name_snapshot, ri.amount_cents"
                " FROM refund_items ri JOIN order_items oi ON oi.id = ri.order_item_id"
                " WHERE ri.refund_id = ANY(:ids) ORDER BY ri.refund_id, ri.order_item_id"
            ),
            {"ids": ids},
        )
        for item in items:
            names[item.refund_id].append(
                RefundItemRow(item.order_item_id, item.product_name_snapshot, item.amount_cents)
            )
    return [RefundRow(**_coerce(dict(row._mapping)), items=tuple(names[row.id])) for row in rows]


def _coerce(values: dict[str, Any]) -> dict[str, Any]:
    """A text query returns the enum columns as strings."""
    return values | {
        "kind": RefundKind(values["kind"]),
        "status": RefundStatus(values["status"]),
        "payment_provider": PaymentProvider(values["payment_provider"]),
    }


async def refund_row(session: AsyncSession, refund_id: UUID) -> RefundRow | None:
    found = await _rows(session, "WHERE r.id = :id", {"id": refund_id})
    return found[0] if found else None


async def refund_page(
    session: AsyncSession,
    filters: RefundFilters,
    *,
    after: tuple[datetime, UUID] | None,
    limit: int,
) -> list[RefundRow]:
    """`queue`: pending or owed, oldest first (`ix_refunds_obligations`); else newest first."""
    clauses: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    if filters.queue:
        clauses.append("(r.status = 'pending' OR (r.status = 'failed' AND r.reissued_at IS NULL))")
    if filters.statuses:
        clauses.append("r.status::text = ANY(:statuses)")
        params["statuses"] = [s.value for s in filters.statuses]
    if filters.kinds:
        clauses.append("r.kind::text = ANY(:kinds)")
        params["kinds"] = [k.value for k in filters.kinds]
    if filters.order_id is not None:
        clauses.append("r.order_id = :order_id")
        params["order_id"] = filters.order_id
    if filters.customer_id is not None:
        clauses.append("o.user_id = :customer_id")
        params["customer_id"] = filters.customer_id
    if filters.created_from is not None:
        clauses.append("r.created_at >= :created_from")
        params["created_from"] = filters.created_from
    if filters.created_to is not None:
        clauses.append("r.created_at < :created_to")
        params["created_to"] = filters.created_to
    direction = ">" if filters.queue else "<"
    if after is not None:
        clauses.append(f"(r.created_at, r.id) {direction} (:after_at, :after_id)")
        params |= {"after_at": after[0], "after_id": after[1]}
    order = "ASC" if filters.queue else "DESC"
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return await _rows(
        session, f"{where} ORDER BY r.created_at {order}, r.id {order} LIMIT :limit", params
    )


async def order_refunds(session: AsyncSession, order_id: UUID) -> list[RefundRow]:
    """Every refund of one order, oldest first (admin order detail, customer summary)."""
    return await _rows(
        session, "WHERE r.order_id = :o ORDER BY r.created_at, r.id", {"o": order_id}
    )
