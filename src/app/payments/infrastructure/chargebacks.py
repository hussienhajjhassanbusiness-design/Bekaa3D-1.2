"""`chargebacks` and `chargeback_items` (VS-030 plan 3.3, ADR-042 d3). Every read that feeds
a money or status decision runs after the caller holds the order's row lock, and checks it.
The display reads below take no lock and never decide money."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import exists, insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.payments.domain.chargebacks import NewChargeback
from app.payments.domain.enums import PaymentProvider
from app.payments.domain.exceptions import ChargebackDuplicateError, ChargebackNotOnlineError
from app.payments.domain.refunds import ChargebackFact, ItemFact
from app.payments.infrastructure.models import ChargebackItemModel, ChargebackModel
from app.payments.infrastructure.order_lock import require_order_lock

_C, _I = ChargebackModel, ChargebackItemModel


class SqlChargebackStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def for_order(self, order_id: UUID) -> list[ChargebackFact]:
        await require_order_lock(self._session, order_id)
        rows = (
            await self._session.execute(
                select(_C.id, _C.payment_id, _C.applied_cents)
                .where(_C.order_id == order_id)
                .order_by(_C.id)
            )
        ).all()
        items: dict[UUID, list[ItemFact]] = defaultdict(list)
        if rows:
            found = await self._session.execute(
                select(_I.chargeback_id, _I.order_item_id, _I.amount_cents)
                .where(_I.chargeback_id.in_([row.id for row in rows]))
                .order_by(_I.chargeback_id, _I.order_item_id)
            )
            for item in found:
                items[item.chargeback_id].append(ItemFact(item.order_item_id, item.amount_cents))
        return [
            ChargebackFact(row.payment_id, row.applied_cents, tuple(items[row.id])) for row in rows
        ]

    async def dispute_exists(self, provider: PaymentProvider, reference: str) -> bool:
        query = select(
            exists().where(
                _C.payment_provider == provider, _C.provider_dispute_reference == reference
            )
        )
        return bool((await self._session.execute(query)).scalar())

    async def insert(self, new: NewChargeback) -> None:
        """The database backs the service: a rival's dispute reference, or a cash payment,
        maps to the same refusal the service gives."""
        try:
            async with self._session.begin_nested():
                await self._insert(new)
        except IntegrityError as exc:
            name = getattr(getattr(exc.orig, "__cause__", None), "constraint_name", None)
            if name == "uq_chargebacks_dispute":
                raise ChargebackDuplicateError("this dispute reference is recorded") from exc
            if name == "ck_chargebacks_online_only":
                raise ChargebackNotOnlineError("a cash payment cannot be charged back") from exc
            raise

    async def _insert(self, new: NewChargeback) -> None:
        await self._session.execute(
            insert(_C).values(
                id=new.id,
                order_id=new.order_id,
                payment_id=new.payment_id,
                payment_provider=new.provider,
                provider_dispute_reference=new.dispute_reference,
                charged_cents=new.charged_cents,
                applied_cents=new.applied_cents,
                excess_cents=new.excess_cents,
                reason=new.reason,
                recorded_by=new.recorded_by,
                received_at=new.received_at,
            )
        )
        if new.items:
            await self._session.execute(
                insert(_I),
                [
                    {
                        "chargeback_id": new.id,
                        "order_id": new.order_id,
                        "order_item_id": item.order_item_id,
                        "amount_cents": item.amount_cents,
                    }
                    for item in new.items
                ],
            )


# --- Reads for responses: no lock; never a phone, hash or address ----------------------


@dataclass(frozen=True)
class ChargebackItemRow:
    order_item_id: UUID
    product_name: str
    amount_cents: int


@dataclass(frozen=True)
class ChargebackRow:
    id: UUID
    order_id: UUID
    order_number: str
    payment_id: UUID
    payment_provider: PaymentProvider
    provider_dispute_reference: str
    charged_cents: int
    applied_cents: int
    excess_cents: int
    currency: str
    reason: str
    recorded_by: UUID
    received_at: datetime
    created_at: datetime
    items: tuple[ChargebackItemRow, ...]


_DETAIL = (
    "SELECT c.id, c.order_id, o.order_number, c.payment_id, c.payment_provider,"
    " c.provider_dispute_reference, c.charged_cents, c.applied_cents, c.excess_cents,"
    " c.currency, c.reason, c.recorded_by, c.received_at, c.created_at"
    " FROM chargebacks c JOIN orders o ON o.id = c.order_id"
)


async def _rows(session: AsyncSession, where: str, params: dict[str, Any]) -> list[ChargebackRow]:
    rows = (await session.execute(text(f"{_DETAIL} {where}"), params)).all()
    names: dict[UUID, list[ChargebackItemRow]] = defaultdict(list)
    if rows:
        items = await session.execute(
            text(
                "SELECT ci.chargeback_id, ci.order_item_id, oi.product_name_snapshot,"
                " ci.amount_cents FROM chargeback_items ci"
                " JOIN order_items oi ON oi.id = ci.order_item_id"
                " WHERE ci.chargeback_id = ANY(:ids) ORDER BY ci.chargeback_id, ci.order_item_id"
            ),
            {"ids": [row.id for row in rows]},
        )
        for item in items:
            names[item.chargeback_id].append(
                ChargebackItemRow(item.order_item_id, item.product_name_snapshot, item.amount_cents)
            )
    return [
        ChargebackRow(
            **(dict(row._mapping) | {"payment_provider": PaymentProvider(row.payment_provider)}),
            items=tuple(names[row.id]),
        )
        for row in rows
    ]


async def chargeback_row(session: AsyncSession, chargeback_id: UUID) -> ChargebackRow | None:
    found = await _rows(session, "WHERE c.id = :id", {"id": chargeback_id})
    return found[0] if found else None


async def order_chargebacks(session: AsyncSession, order_id: UUID) -> list[ChargebackRow]:
    """Every chargeback of one order, oldest first (admin only: never on the customer's)."""
    return await _rows(
        session, "WHERE c.order_id = :o ORDER BY c.created_at, c.id", {"o": order_id}
    )
