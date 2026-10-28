"""Negotiation's published surface for other contexts and the worker. Another context imports
only this or `app.negotiation.application.ports` (`tests/unit/test_deep_architecture.py`)."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.catalog.public import cart_product_reader
from app.negotiation.application.ports import PaymentInFlight
from app.negotiation.application.services.erase_offers import (
    blank_customer_messages,
    lock_live_offers,
    withdraw_live_offers,
)
from app.negotiation.application.services.expire_offers import (
    expire_checkout_offer,
    expire_offer,
    remind_offer,
)
from app.negotiation.application.services.offer_checkout import (
    lock_for_checkout,
    read_for_checkout,
)
from app.negotiation.application.services.settle_offers import StlPurchase, settle_stl_purchases
from app.negotiation.domain.exceptions import (
    OfferCheckoutExpiredError,
    OfferInvalidTransitionError,
    OfferNotFoundError,
)
from app.negotiation.domain.offers import Offer
from app.negotiation.infrastructure.adapters import EngagementOfferNotifier, PlatformOfferMailer
from app.negotiation.infrastructure.data_export import ExportOfferRow, offers_for_export
from app.negotiation.infrastructure.offers import SqlOfferStore
from app.negotiation.infrastructure.reports import live_offer_counts
from app.ordering.application.ports import AcceptedOffer
from app.ordering.public import OfferCheckoutExpiredError as OfferCheckoutExpired
from app.ordering.public import OfferCheckoutNotFoundError as OfferCheckoutNotFound
from app.ordering.public import OfferNotCheckoutableError as OfferNotCheckoutable
from app.platform.public import SqlAuditWriter

__all__ = [
    "ExportOfferRow",
    "PaymentInFlight",
    "SqlOfferCheckouts",
    "StlPurchase",
    "blank_offer_messages_for_erasure",
    "expire_overdue_offers",
    "live_offer_counts",
    "lock_live_offers_for_erasure",
    "offers_for_export",
    "settle_offers_on_stl_purchase",
    "withdraw_offers_for_erasure",
]

logger = structlog.get_logger()


class SqlOfferCheckouts:
    """Ordering's `OfferCheckouts` port (VS-041), on the caller's session."""

    def __init__(self, session: AsyncSession) -> None:
        self._offers = SqlOfferStore(session)

    async def read(self, offer_id: UUID, user_id: UUID, *, now: datetime) -> AcceptedOffer:
        return await _terms(
            read_for_checkout(self._offers, offer_id=offer_id, user_id=user_id, now=now)
        )

    async def lock(
        self, offer_id: UUID, user_id: UUID, *, clock: Callable[[], datetime]
    ) -> AcceptedOffer:
        return await _terms(
            lock_for_checkout(self._offers, offer_id=offer_id, user_id=user_id, clock=clock)
        )


async def _terms(found: Awaitable[Offer]) -> AcceptedOffer:
    """Negotiation's refusals as Ordering's, so the checkout route maps one family."""
    try:
        offer = await found
    except OfferNotFoundError as exc:
        raise OfferCheckoutNotFound() from exc
    except OfferCheckoutExpiredError as exc:
        raise OfferCheckoutExpired() from exc
    except OfferInvalidTransitionError as exc:
        raise OfferNotCheckoutable(exc.status.value) from exc
    if offer.agreed_amount_cents is None or offer.checkout_expires_at is None:
        raise OfferNotCheckoutable(offer.status.value)  # ck_offers_accepted_shape forbids it
    return AcceptedOffer(
        id=offer.id,
        product_id=offer.product_id,
        agreed_amount_cents=offer.agreed_amount_cents,
        currency=offer.currency,
        checkout_expires_at=offer.checkout_expires_at,
    )


async def settle_offers_on_stl_purchase(
    session: AsyncSession, purchases: list[StlPurchase], *, at: datetime
) -> None:
    """In the payment's transaction, after its orders, lines and payment locks (ADR-037)."""
    await settle_stl_purchases(SqlOfferStore(session), SqlAuditWriter(session), purchases, now=at)


async def expire_overdue_offers(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    limit: int,
    in_flight: Callable[[AsyncSession], PaymentInFlight],
) -> dict[str, int]:
    """Three passes - inactivity, checkout window, reminders - each SRS 20.8's batch shape:
    candidates without a lock, then one short lock-and-recheck transaction per offer."""

    async def expire_one(session: AsyncSession, offer_id: UUID) -> bool:
        notifier, audit = EngagementOfferNotifier(session), SqlAuditWriter(session)
        return await expire_offer(
            SqlOfferStore(session), notifier, audit, offer_id=offer_id, now=now
        )

    async def close_checkout(session: AsyncSession, offer_id: UUID) -> bool:
        notifier, audit = EngagementOfferNotifier(session), SqlAuditWriter(session)
        return await expire_checkout_offer(
            SqlOfferStore(session), notifier, audit, in_flight(session), offer_id=offer_id, now=now
        )

    async def remind(session: AsyncSession, offer_id: UUID) -> bool:
        return await remind_offer(
            SqlOfferStore(session),
            await cart_product_reader(session),
            EngagementOfferNotifier(session),
            PlatformOfferMailer(session),
            offer_id=offer_id,
            now=now,
        )

    async with session_factory() as session, session.begin():
        store = SqlOfferStore(session)
        overdue = await store.overdue_ids(now, limit)
        reminders = await store.reminder_due_ids(now, limit)
    expired = await _each(session_factory, overdue, expire_one)
    seen, closed = await _checkout_pass(session_factory, now, limit, close_checkout)
    return {
        "candidates": len(overdue),
        "expired": expired,
        "checkout_candidates": seen,
        "checkout_expired": closed,
        "reminded": await _each(session_factory, reminders, remind),
    }


async def _checkout_pass(
    session_factory: async_sessionmaker[AsyncSession],
    now: datetime,
    limit: int,
    close: Callable[[AsyncSession, UUID], Awaitable[bool]],
) -> tuple[int, int]:
    """Pages past offers left for a payment in flight, so they never stall the rest
    (ADR-037 d7); stops at `limit` closed or at a short page."""
    seen = closed = 0
    after: tuple[datetime, UUID] | None = None
    while closed < limit:
        async with session_factory() as session, session.begin():
            page = await SqlOfferStore(session).checkout_overdue_ids(now, limit, after=after)
        seen += len(page)
        closed += await _each(session_factory, [offer_id for _, offer_id in page], close)
        if len(page) < limit:
            break
        after = page[-1]
    return seen, closed


async def _each(
    session_factory: async_sessionmaker[AsyncSession],
    ids: list[UUID],
    step: Callable[[AsyncSession, UUID], Awaitable[bool]],
) -> int:
    """One rolled-back failure is logged and skipped, so one bad row never stalls the rest."""
    done = 0
    for offer_id in ids:
        try:
            async with session_factory() as session, session.begin():
                done += await step(session, offer_id)
        except (OSError, DBAPIError) as exc:
            if isinstance(exc, OSError) or exc.connection_invalidated:
                raise
            await logger.aexception("expire_offers_step_failed", offer_id=str(offer_id))
        except Exception:
            await logger.aexception("expire_offers_step_failed", offer_id=str(offer_id))
    return done


async def lock_live_offers_for_erasure(session: AsyncSession, user_id: UUID) -> None:
    """VS-045: after the orders and cart locks, before the user row (ADR-047)."""
    await lock_live_offers(SqlOfferStore(session), user_id)


async def blank_offer_messages_for_erasure(session: AsyncSession, user_id: UUID) -> int:
    return await blank_customer_messages(SqlOfferStore(session), user_id)


async def withdraw_offers_for_erasure(session: AsyncSession, user_id: UUID, *, at: datetime) -> int:
    return await withdraw_live_offers(SqlOfferStore(session), user_id, now=at)
