"""`SqlOfferStore`: offers and their append-only rounds. No method updates or deletes a round."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, case, func, insert, literal, select, tuple_, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.negotiation.application.ports import (
    AdminOfferFilters,
    CustomerOfferFilters,
    QueuedOffer,
    QueueKey,
)
from app.negotiation.domain.enums import AWAITING_STATUSES, OfferStatus
from app.negotiation.domain.exceptions import OfferAlreadyActiveError
from app.negotiation.domain.offers import NewOffer, NewRound, Offer, OfferRound
from app.negotiation.infrastructure.models import OfferModel, OfferRoundModel

_O, _R = OfferModel, OfferRoundModel
_LIVE_INDEX = "uq_offers_live"
_OFFER_COLUMNS = (
    _O.id,
    _O.user_id,
    _O.product_id,
    _O.status,
    _O.turn,
    _O.initial_amount_cents,
    _O.current_amount_cents,
    _O.agreed_amount_cents,
    _O.currency,
    _O.responds_by,
    _O.accepted_at,
    _O.checkout_expires_at,
    _O.rejected_at,
    _O.cooldown_until,
    _O.created_at,
    _O.updated_at,
    _O.remind_at,
)
_ROUND_COLUMNS = (
    _R.id,
    _R.offer_id,
    _R.sequence,
    _R.actor,
    _R.action,
    _R.amount_cents,
    _R.currency,
    _R.message,
    _R.created_at,
)
# ADR-034: the administrator's turn first, then the customer's, soonest deadline first;
# then accepted, then closed offers, oldest first.
_QUEUE_RANK = case(
    (_O.status == OfferStatus.AWAITING_ADMIN, 0),
    (_O.status == OfferStatus.AWAITING_CUSTOMER, 1),
    (_O.status == OfferStatus.ACCEPTED, 2),
    else_=3,
)
_QUEUE_AT = case((_O.status.in_(AWAITING_STATUSES), _O.responds_by), else_=_O.created_at)


def _offer(row: Any) -> Offer:
    return Offer(**{c.key: getattr(row, c.key) for c in _OFFER_COLUMNS})


def _violates_live_index(error: IntegrityError) -> bool:
    """By the driver's constraint name, as catalog's `_violates`; never a CHECK as 409."""
    name = getattr(getattr(error.orig, "__cause__", None), "constraint_name", None)
    return name == _LIVE_INDEX if isinstance(name, str) else _LIVE_INDEX in str(error.orig)


class SqlOfferStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, offer: NewOffer, *, at: datetime) -> Offer:
        try:
            async with self._session.begin_nested():
                row = (
                    await self._session.execute(
                        insert(_O)
                        .values(
                            user_id=offer.user_id,
                            product_id=offer.product_id,
                            status=offer.status,
                            turn=offer.turn,
                            initial_amount_cents=offer.amount_cents,
                            current_amount_cents=offer.amount_cents,
                            currency=offer.currency,
                            responds_by=offer.responds_by,
                            created_at=at,
                            updated_at=at,
                        )
                        .returning(*_OFFER_COLUMNS)
                    )
                ).one()
                await self.add_round(row.id, offer.first_round, at=at)
        except IntegrityError as exc:
            if _violates_live_index(exc):
                raise OfferAlreadyActiveError() from exc
            raise
        return _offer(row)

    async def cooldowns(self, user_id: UUID, product_id: UUID) -> list[datetime]:
        stmt = select(_O.cooldown_until).where(
            _O.user_id == user_id,
            _O.product_id == product_id,
            _O.status == OfferStatus.REJECTED,
            _O.cooldown_until.is_not(None),
        )
        return [moment for moment in (await self._session.scalars(stmt)).all() if moment]

    async def get(self, offer_id: UUID, *, user_id: UUID | None = None) -> Offer | None:
        stmt = select(*_OFFER_COLUMNS).where(_O.id == offer_id)
        if user_id is not None:
            stmt = stmt.where(_O.user_id == user_id)
        row = (await self._session.execute(stmt)).first()
        return _offer(row) if row is not None else None

    async def rounds(self, offer_id: UUID) -> list[OfferRound]:
        stmt = select(*_ROUND_COLUMNS).where(_R.offer_id == offer_id).order_by(_R.sequence)
        return [
            OfferRound(**{c.key: getattr(row, c.key) for c in _ROUND_COLUMNS})
            for row in (await self._session.execute(stmt)).all()
        ]

    async def customer_page(
        self,
        user_id: UUID,
        filters: CustomerOfferFilters,
        *,
        after: tuple[datetime, UUID] | None,
        limit: int,
    ) -> list[Offer]:
        stmt = select(*_OFFER_COLUMNS).where(_O.user_id == user_id)
        if filters.status is not None:
            stmt = stmt.where(_O.status == filters.status)
        if filters.product_id is not None:
            stmt = stmt.where(_O.product_id == filters.product_id)
        if after is not None:
            stmt = stmt.where(tuple_(_O.created_at, _O.id) < tuple_(*after))
        stmt = stmt.order_by(_O.created_at.desc(), _O.id.desc()).limit(limit)
        return [_offer(row) for row in (await self._session.execute(stmt)).all()]

    async def queue_page(
        self, filters: AdminOfferFilters, *, after: QueueKey | None, limit: int
    ) -> list[QueuedOffer]:
        stmt = select(*_OFFER_COLUMNS, _QUEUE_RANK.label("rank"), _QUEUE_AT.label("sort_at"))
        if filters.status is not None:
            stmt = stmt.where(_O.status == filters.status)
        if filters.product_id is not None:
            stmt = stmt.where(_O.product_id == filters.product_id)
        if filters.user_id is not None:
            stmt = stmt.where(_O.user_id == filters.user_id)
        if filters.responds_before is not None:
            # A closed offer keeps its old deadline; only a pending one is "due".
            stmt = stmt.where(
                _O.status.in_(AWAITING_STATUSES), _O.responds_by < filters.responds_before
            )
        if after is not None:
            rank, at, offer_id = after
            stmt = stmt.where(
                tuple_(_QUEUE_RANK, _QUEUE_AT, _O.id)
                > tuple_(
                    literal(rank),
                    literal(at, DateTime(timezone=True)),
                    literal(offer_id, postgresql.UUID()),
                )
            )
        stmt = stmt.order_by(_QUEUE_RANK, _QUEUE_AT, _O.id).limit(limit)
        return [
            QueuedOffer(_offer(row), (row.rank, row.sort_at, row.id))
            for row in (await self._session.execute(stmt)).all()
        ]

    async def overdue_ids(self, now: datetime, limit: int) -> list[UUID]:
        stmt = (
            select(_O.id)
            .where(_O.status.in_(AWAITING_STATUSES), _O.responds_by <= now)
            .order_by(_O.responds_by, _O.id)
            .limit(limit)
        )
        return list((await self._session.scalars(stmt)).all())

    async def checkout_overdue_ids(self, now: datetime, limit: int) -> list[UUID]:
        stmt = (
            select(_O.id)
            .where(_O.status == OfferStatus.ACCEPTED, _O.checkout_expires_at <= now)
            .order_by(_O.checkout_expires_at, _O.id)
            .limit(limit)
        )
        return list((await self._session.scalars(stmt)).all())

    async def reminder_due_ids(self, now: datetime, limit: int) -> list[UUID]:
        stmt = (
            select(_O.id)
            .where(_O.remind_at.is_not(None), _O.remind_at <= now)
            .order_by(_O.remind_at, _O.id)
            .limit(limit)
        )
        return list((await self._session.scalars(stmt)).all())

    async def lock(self, offer_id: UUID, *, user_id: UUID | None = None) -> Offer | None:
        stmt = select(*_OFFER_COLUMNS).where(_O.id == offer_id)
        if user_id is not None:
            stmt = stmt.where(_O.user_id == user_id)
        row = (await self._session.execute(stmt.with_for_update())).first()
        return _offer(row) if row is not None else None

    async def lock_unless_locked(self, offer_id: UUID) -> Offer | None:
        stmt = select(*_OFFER_COLUMNS).where(_O.id == offer_id).with_for_update(skip_locked=True)
        row = (await self._session.execute(stmt)).first()
        return _offer(row) if row is not None else None

    async def save_state(self, offer: Offer) -> None:
        await self._session.execute(
            update(_O)
            .where(_O.id == offer.id)
            .values(
                status=offer.status,
                turn=offer.turn,
                current_amount_cents=offer.current_amount_cents,
                agreed_amount_cents=offer.agreed_amount_cents,
                responds_by=offer.responds_by,
                accepted_at=offer.accepted_at,
                checkout_expires_at=offer.checkout_expires_at,
                rejected_at=offer.rejected_at,
                cooldown_until=offer.cooldown_until,
                remind_at=offer.remind_at,
                updated_at=offer.updated_at,
            )
        )

    async def add_round(self, offer_id: UUID, new: NewRound, *, at: datetime) -> None:
        await self._session.execute(
            insert(_R).values(
                offer_id=offer_id,
                sequence=new.sequence,
                actor=new.actor,
                action=new.action,
                amount_cents=new.amount_cents,
                currency=new.currency,
                message=new.message,
                created_at=at,
            )
        )

    async def next_sequence(self, offer_id: UUID) -> int:
        stmt = select(func.coalesce(func.max(_R.sequence), 0) + 1).where(_R.offer_id == offer_id)
        return int(await self._session.scalar(stmt) or 1)
