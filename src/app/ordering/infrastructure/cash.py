"""Cash eligibility reads and the block store (VS-028 plan 3.5; ADR-024 d6, d9)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, func, literal, select, tuple_, union, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.domain.admin_orders import CashBlock
from app.ordering.domain.cash import CASH_PHONE_LOCK_NS, SELF_CANCEL_WINDOW
from app.ordering.domain.enums import CancelReason, OrderStatus, PaymentMethod
from app.ordering.infrastructure.models import CashPaymentBlockModel, OrderModel

_B, _O = CashPaymentBlockModel, OrderModel
_BLOCK_COLUMNS = (
    _B.id,
    _B.user_id,
    _B.order_id,
    _O.order_number,
    _B.reason,
    _B.created_at,
    _B.cleared_at,
    _B.cleared_by,
)


async def lock_cash_phone(session: AsyncSession, phone_hash: str) -> None:
    """Transaction-scoped two-int advisory lock; released at COMMIT or ROLLBACK."""
    await session.execute(
        select(func.pg_advisory_xact_lock(CASH_PHONE_LOCK_NS, func.hashtext(phone_hash)))
    )


class SqlCashChecks:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_phone(self, phone_hash: str) -> None:
        await lock_cash_phone(self._session, phone_hash)

    async def active_block(self, user_id: UUID, phone_hash: str) -> bool:
        by_user = exists().where(_B.user_id == user_id, _B.cleared_at.is_(None))
        by_phone = exists().where(_B.contact_phone_hash == phone_hash, _B.cleared_at.is_(None))
        stmt = select(by_user).union_all(select(by_phone))
        return any((await self._session.execute(stmt)).scalars())

    async def open_order_count(self, user_id: UUID, phone_hash: str, *, at: datetime) -> int:
        """Each branch matches one partial index; an order counts once (ADR-038 d23)."""
        cash = _O.payment_method == PaymentMethod.CASH
        open_cash = (cash, _O.status == OrderStatus.IN_PROGRESS)
        self_cancelled = (cash, _O.customer_cancelled_at > at - SELF_CANCEL_WINDOW)
        ids = union(
            select(_O.id).where(*open_cash, _O.user_id == user_id),
            select(_O.id).where(*open_cash, _O.contact_phone_hash == phone_hash),
            select(_O.id).where(*self_cancelled, _O.user_id == user_id),
            select(_O.id).where(*self_cancelled, _O.contact_phone_hash == phone_hash),
        ).subquery()
        return (await self._session.execute(select(func.count()).select_from(ids))).scalar_one()


class SqlCashBlockStore:
    """The interface VS-029 and VS-031 extend; the caller of `insert_block` holds the phone lock."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_block(
        self,
        *,
        user_id: UUID,
        phone_hash: str,
        order_id: UUID,
        reason: CancelReason,
        at: datetime,
    ) -> bool:
        stmt = (
            postgresql.insert(_B)
            .values(
                user_id=user_id,
                contact_phone_hash=phone_hash,
                order_id=order_id,
                reason=reason,
                created_at=at,
            )
            .on_conflict_do_nothing(index_elements=[_B.order_id])
            .returning(literal(1))
        )
        return (await self._session.execute(stmt)).first() is not None

    async def page(
        self,
        *,
        user_id: UUID | None,
        active: bool | None,
        phone_hash: str | None,
        after: tuple[datetime, UUID] | None,
        limit: int,
    ) -> list[CashBlock]:
        """Newest first by `(created_at, id)`. No lock."""
        query = select(*_BLOCK_COLUMNS).join(_O, _O.id == _B.order_id)
        if user_id is not None:
            query = query.where(_B.user_id == user_id)
        if phone_hash is not None:
            query = query.where(_B.contact_phone_hash == phone_hash)
        if active is not None:
            query = query.where(_B.cleared_at.is_(None) if active else _B.cleared_at.is_not(None))
        if after is not None:
            query = query.where(tuple_(_B.created_at, _B.id) < tuple_(*after))
        query = query.order_by(_B.created_at.desc(), _B.id.desc()).limit(limit)
        return [CashBlock(*row) for row in (await self._session.execute(query)).all()]

    async def lock(self, block_id: UUID) -> CashBlock | None:
        row = (
            await self._session.execute(
                select(*_BLOCK_COLUMNS)
                .join(_O, _O.id == _B.order_id)
                .where(_B.id == block_id)
                .with_for_update(of=_B)
            )
        ).first()
        return CashBlock(*row) if row is not None else None

    async def clear(self, block_id: UUID, *, admin_id: UUID, at: datetime) -> None:
        """Only an uncleared block; the caller holds `lock`."""
        await self._session.execute(
            update(_B)
            .where(_B.id == block_id, _B.cleared_at.is_(None))
            .values(cleared_at=at, cleared_by=admin_id)
        )
