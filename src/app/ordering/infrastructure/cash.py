"""Cash eligibility reads and the block store (VS-028 plan 3.5; ADR-024 d6, d9)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, func, literal, select, union
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.domain.cash import CASH_PHONE_LOCK_NS
from app.ordering.domain.enums import CancelReason, OrderStatus, PaymentMethod
from app.ordering.infrastructure.models import CashPaymentBlockModel, OrderModel

_B, _O = CashPaymentBlockModel, OrderModel


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

    async def open_order_count(self, user_id: UUID, phone_hash: str) -> int:
        open_cash = (
            _O.payment_method == PaymentMethod.CASH,
            _O.status == OrderStatus.IN_PROGRESS,
        )
        ids = union(
            select(_O.id).where(*open_cash, _O.user_id == user_id),
            select(_O.id).where(*open_cash, _O.contact_phone_hash == phone_hash),
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
