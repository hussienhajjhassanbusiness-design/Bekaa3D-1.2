"""`SqlPaymentStore`, and `SqlPaymentAttempts`: the adapter for Ordering's
`PaymentAttempts` port (VS-023 plan 3.0). Neither commits."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.application.ports import PaymentAttemptRef
from app.payments.application.ports import PaymentProviderPort
from app.payments.domain.enums import PaymentProvider, PaymentStatus
from app.payments.domain.payments import Payment
from app.payments.infrastructure.models import PaymentModel

_P = PaymentModel
_COLUMNS = (
    _P.id,
    _P.order_id,
    _P.provider,
    _P.status,
    _P.amount_cents,
    _P.currency,
    _P.provider_payment_id,
    _P.late_captured_at,
)


def _payment(row: Any) -> Payment:
    return Payment(**{column.key: getattr(row, column.key) for column in _COLUMNS})


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
                .returning(*_COLUMNS)
            )
        ).one()
        return _payment(row)

    async def get(self, payment_id: UUID) -> Payment | None:
        row = (await self._session.execute(select(*_COLUMNS).where(_P.id == payment_id))).first()
        return _payment(row) if row is not None else None

    async def lock(self, payment_id: UUID) -> Payment | None:
        row = (
            await self._session.execute(
                select(*_COLUMNS).where(_P.id == payment_id).with_for_update()
            )
        ).first()
        return _payment(row) if row is not None else None

    async def find_by_reference(
        self, provider: PaymentProvider, provider_payment_id: str
    ) -> Payment | None:
        row = (
            await self._session.execute(
                select(*_COLUMNS).where(
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

    async def mark_paid(self, payment_id: UUID, *, at: datetime) -> None:
        await self._session.execute(
            update(_P)
            .where(_P.id == payment_id)
            .values(status=PaymentStatus.PAID, verified_at=at, updated_at=at)
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

    async def mark_late_capture(self, payment_id: UUID, *, at: datetime, fail: bool) -> None:
        values: dict[str, Any] = {"late_captured_at": at, "updated_at": at}
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


class SqlPaymentAttempts:
    """Ordering's `PaymentAttempts`: the configured providers and the pending INSERT."""

    def __init__(self, session: AsyncSession, providers: Mapping[str, PaymentProviderPort]) -> None:
        self._store = SqlPaymentStore(session)
        self._providers = providers

    def configured_providers(self) -> frozenset[str]:
        return frozenset(self._providers)

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
        return PaymentAttemptRef(
            id=payment.id,
            provider=payment.provider.value,
            status=payment.status.value,
            amount_cents=payment.amount_cents,
            currency=payment.currency,
        )
