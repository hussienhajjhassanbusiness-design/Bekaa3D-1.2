"""What every offer write route builds: the adapters on the request's session and the
request's audit context."""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip
from app.core.security import hash_ip
from app.negotiation.application.ports import CartProductReader
from app.negotiation.application.services.respond_to_offer import OfferDeps
from app.negotiation.application.services.submit_offer import OfferRequestContext
from app.negotiation.infrastructure.adapters import (
    EngagementOfferNotifier,
    OrderingStlOwnership,
    PlatformOfferMailer,
)
from app.negotiation.infrastructure.offers import SqlOfferStore
from app.platform.public import SqlAuditWriter, settings_reader


def offer_deps(session: AsyncSession, products: CartProductReader) -> OfferDeps:
    return OfferDeps(
        offers=SqlOfferStore(session),
        products=products,
        ownership=OrderingStlOwnership(session),
        settings=settings_reader(session),
        notifier=EngagementOfferNotifier(session),
        mailer=PlatformOfferMailer(session),
        audit=SqlAuditWriter(session),
    )


def request_context(request: Request) -> OfferRequestContext:
    ip = client_ip(request)
    return OfferRequestContext(
        request_id=getattr(request.state, "request_id", None),
        ip_hash=hash_ip(ip) if ip else None,
    )
