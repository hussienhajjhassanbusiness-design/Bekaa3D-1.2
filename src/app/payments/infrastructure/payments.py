"""`SqlPaymentStore`, and `SqlPaymentAttempts`: the adapter for Ordering's
`PaymentAttempts` port (VS-023 plan 3.0). Neither commits."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, insert, select, tuple_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.application.ports import PaymentAttemptRef
from app.ordering.public import LiveAttemptExistsError
from app.payments.application.ports import PaymentProviderPort
from app.payments.domain.enums import PaymentProvider, PaymentStatus
from app.payments.domain.outcome import LIVE
from app.payments.domain.payments import Payment
from app.payments.infrastructure.models import PaymentModel

_P = PaymentModel
ONE_LIVE_INDEX = "uq_payments_one_live"
_COLUMNS = (
    _P.id,
    _P.order_id,
    _P.provider,
    _P.status,
    _P.amount_cents,
    _P.currency,
    _P.provider_payment_id,
    _P.late_captured_at,
    _P.initiated_at,
    _P.captured_amount_cents,
    _P.captured_currency,
)
_SELECT = (*_COLUMNS, _P.provider_metadata["redirect_url"].astext.label("redirect_url"))


def _payment(row: Any) -> Payment:
    fields = {column.key: getattr(row, column.key) for column in _COLUMNS}
    return Payment(**fields, redirect_url=row.redirect_url)


class SqlPaymentStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_pending(
        self,
        *,
        order_id: UUID,
        provider: PaymentProvider,
        amount_cents: int,
        currency: str,
        at: datetime,
    ) -> Payment:
        row = (
            await self._session.execute(
                insert(_P)
                .values(
                    order_id=order_id,
                    provider=provider,
                    order_payment_method="online",
                    status=PaymentStatus.PENDING,
                    amount_cents=amount_cents,
                    currency=currency,
                    initiated_at=at,
                )
                .returning(*_SELECT)
            )
        ).one()
        return _payment(row)

    async def get(self, payment_id: UUID) -> Payment | None:
        row = (await self._session.execute(select(*_SELECT).where(_P.id == payment_id))).first()
        return _payment(row) if row is not None else None

    async def lock(self, payment_id: UUID) -> Payment | None:
        row = (
            await self._session.execute(
                select(*_SELECT).where(_P.id == payment_id).with_for_update()
            )
        ).first()
        return _payment(row) if row is not None else None

    async def lock_reference(self, provider: PaymentProvider, provider_payment_id: str) -> None:
        """Serialises two confirms typing one reference, so the second sees the first's row
        instead of tripping `uq_payments_provider_reference`; taken after the payment lock."""
        key = func.hashtextextended(f"payment_reference:{provider}:{provider_payment_id}", 0)
        await self._session.execute(select(func.pg_advisory_xact_lock(key)))

    async def find_by_reference(
        self, provider: PaymentProvider, provider_payment_id: str
    ) -> Payment | None:
        row = (
            await self._session.execute(
                select(*_SELECT).where(
                    _P.provider == provider, _P.provider_payment_id == provider_payment_id
                )
            )
        ).first()
        return _payment(row) if row is not None else None

    async def set_provider_reference(
        self, payment_id: UUID, provider_payment_id: str, *, redirect_url: str | None, at: datetime
    ) -> None:
        """Only while no reference is stored: a verification may have stored it first."""
        await self._session.execute(
            update(_P)
            .where(_P.id == payment_id, _P.provider_payment_id.is_(None))
            .values(
                provider_payment_id=provider_payment_id,
                provider_metadata={"redirect_url": redirect_url},
                updated_at=at,
            )
        )

    async def mark_failed(self, payment_id: UUID, *, at: datetime) -> None:
        """Only a still-pending attempt; never undoes a verified result."""
        await self._session.execute(
            update(_P)
            .where(_P.id == payment_id, _P.status == PaymentStatus.PENDING)
            .values(status=PaymentStatus.FAILED, failed_at=at, updated_at=at)
        )

    async def mark_paid(
        self,
        payment_id: UUID,
        *,
        at: datetime,
        captured_amount_cents: int | None,
        captured_currency: str | None,
    ) -> None:
        await self._session.execute(
            update(_P)
            .where(_P.id == payment_id)
            .values(
                status=PaymentStatus.PAID,
                verified_at=at,
                updated_at=at,
                captured_amount_cents=captured_amount_cents,
                captured_currency=captured_currency,
            )
        )

    async def mark_status(self, payment_id: UUID, status: PaymentStatus, *, at: datetime) -> None:
        stamps = {
            PaymentStatus.FAILED: {"failed_at": at},
            PaymentStatus.EXPIRED: {"expired_at": at},
        }
        await self._session.execute(
            update(_P)
            .where(_P.id == payment_id)
            .values(status=status, updated_at=at, **stamps.get(status, {}))
        )

    async def mark_late_capture(
        self,
        payment_id: UUID,
        *,
        at: datetime,
        fail: bool,
        captured_amount_cents: int | None,
        captured_currency: str | None,
    ) -> None:
        values: dict[str, Any] = {
            "late_captured_at": at,
            "updated_at": at,
            "captured_amount_cents": captured_amount_cents,
            "captured_currency": captured_currency,
        }
        if fail:
            values |= {"status": PaymentStatus.FAILED, "failed_at": at}
        await self._session.execute(
            update(_P).where(_P.id == payment_id, _P.late_captured_at.is_(None)).values(**values)
        )

    async def fill_provider_reference(
        self, payment_id: UUID, provider_payment_id: str, *, at: datetime
    ) -> None:
        """Under the payment lock, only when checkout's Tx2 never stored it."""
        await self._session.execute(
            update(_P)
            .where(_P.id == payment_id, _P.provider_payment_id.is_(None))
            .values(provider_payment_id=provider_payment_id, updated_at=at)
        )

    async def lock_for_order(self, order_id: UUID) -> list[Payment]:
        rows = await self._session.execute(
            select(*_SELECT).where(_P.order_id == order_id).order_by(_P.id).with_for_update()
        )
        return [_payment(row) for row in rows]

    async def for_order(self, order_id: UUID) -> list[Payment]:
        """Every attempt of the order by `(initiated_at, id)`. No lock (release Tx A)."""
        rows = await self._session.execute(
            select(*_SELECT).where(_P.order_id == order_id).order_by(_P.initiated_at, _P.id)
        )
        return [_payment(row) for row in rows]

    async def live_for_order(self, order_id: UUID) -> Payment | None:
        row = (
            await self._session.execute(
                select(*_SELECT).where(_P.order_id == order_id, _P.status.in_(LIVE))
            )
        ).first()
        return _payment(row) if row is not None else None

    async def previous_provider(self, order_id: UUID) -> PaymentProvider | None:
        provider: PaymentProvider | None = await self._session.scalar(
            select(_P.provider)
            .where(_P.order_id == order_id)
            .order_by(_P.initiated_at.desc(), _P.id.desc())
            .limit(1)
        )
        return provider

    async def stale_live_ids(
        self, *, before: datetime, after: tuple[datetime, UUID] | None, limit: int
    ) -> list[tuple[datetime, UUID]]:
        """Served by `ix_payments_unsettled`; cash is never live (`ck_payments_cash_shape`)."""
        query = stale_live_query(before=before, after=after, limit=limit)
        return [(row.initiated_at, row.id) for row in await self._session.execute(query)]


def stale_live_query(
    *, before: datetime, after: tuple[datetime, UUID] | None, limit: int
) -> Select[datetime, UUID]:
    """The reconcile job's selection, also EXPLAINed by its test (plan 6.2)."""
    query = select(_P.initiated_at, _P.id).where(
        _P.status.in_(LIVE), _P.order_payment_method == "online", _P.initiated_at <= before
    )
    if after is not None:
        query = query.where(tuple_(_P.initiated_at, _P.id) > after)
    return query.order_by(_P.initiated_at, _P.id).limit(limit)


class SqlPaymentAttempts:
    """Ordering's `PaymentAttempts`: the configured providers, the attempts, the INSERT."""

    def __init__(self, session: AsyncSession, providers: Mapping[str, PaymentProviderPort]) -> None:
        self._session = session
        self._store = SqlPaymentStore(session)
        self._providers = providers

    def configured_providers(self) -> frozenset[str]:
        return frozenset(self._providers)

    async def live_attempt(self, order_id: UUID) -> PaymentAttemptRef | None:
        payment = await self._store.live_for_order(order_id)
        return _ref(payment) if payment is not None else None

    async def previous_provider(self, order_id: UUID) -> str | None:
        provider = await self._store.previous_provider(order_id)
        return provider.value if provider is not None else None

    async def count_latest_on(self, order_ids: Sequence[UUID], provider: str) -> int:
        if not order_ids:
            return 0
        latest = (
            select(_P.provider)
            .where(_P.order_id.in_(order_ids))
            .distinct(_P.order_id)
            .order_by(_P.order_id, _P.initiated_at.desc().nulls_last(), _P.id.desc())
            .subquery()
        )
        count = await self._session.scalar(
            select(func.count())
            .select_from(latest)
            .where(latest.c.provider == PaymentProvider(provider))
        )
        return int(count or 0)

    async def open_attempt(
        self, *, order_id: UUID, amount_cents: int, currency: str, provider: str, at: datetime
    ) -> PaymentAttemptRef:
        payment = await self._store.insert_pending(
            order_id=order_id,
            provider=PaymentProvider(provider),
            amount_cents=amount_cents,
            currency=currency,
            at=at,
        )
        return _ref(payment)

    async def open_retry_attempt(
        self, *, order_id: UUID, amount_cents: int, currency: str, provider: str, at: datetime
    ) -> PaymentAttemptRef:
        try:
            async with self._session.begin_nested():
                payment = await self._store.insert_pending(
                    order_id=order_id,
                    provider=PaymentProvider(provider),
                    amount_cents=amount_cents,
                    currency=currency,
                    at=at,
                )
        except IntegrityError as exc:
            if _constraint(exc) == ONE_LIVE_INDEX:
                raise LiveAttemptExistsError(str(order_id)) from exc
            raise
        return _ref(payment)


def _constraint(error: IntegrityError) -> str | None:
    """The driver's own constraint name, as `SqlOrderStore` reads it."""
    name = getattr(getattr(error.orig, "__cause__", None), "constraint_name", None)
    return name if isinstance(name, str) else None


def _ref(payment: Payment) -> PaymentAttemptRef:
    return PaymentAttemptRef(
        id=payment.id,
        provider=payment.provider.value,
        status=payment.status.value,
        amount_cents=payment.amount_cents,
        currency=payment.currency,
        redirect_url=payment.redirect_url,
    )
