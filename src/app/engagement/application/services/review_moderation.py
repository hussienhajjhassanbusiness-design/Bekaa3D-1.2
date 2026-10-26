"""Review hide and restore (VS-037 plan 3.3). Lock order: the product (FOR NO KEY UPDATE),
then the review row (FOR UPDATE); no `R_user`, the badge is not touched (plan 8.1)."""

from dataclasses import replace
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from app.engagement.application.commands.custom_request_pipeline import AdminContext
from app.engagement.application.ports import ReviewableProducts, ReviewModerationStore
from app.engagement.application.services.reviews import recompute_rating
from app.engagement.domain.exceptions import ReviewModerationConflictError, ReviewNotFoundError
from app.engagement.domain.reviews import Review
from app.platform.application.ports.audit_writer import AuditWriter

REVIEW_ENTITY_TYPE: Final = "review"


def _state(is_hidden: bool, hidden_at: datetime | None, product_id: UUID) -> dict[str, Any]:
    """The audit payload (D8): moderation state only, never the text or the author."""
    return {
        "is_hidden": is_hidden,
        "hidden_at": hidden_at.isoformat() if hidden_at is not None else None,
        "product_id": str(product_id),
    }


async def moderate_review(
    store: ReviewModerationStore,
    products: ReviewableProducts,
    audit: AuditWriter,
    *,
    review_id: UUID,
    hide: bool,
    reason: str | None,
    now: datetime,
    context: AdminContext,
) -> Review:
    """A deleted review is missing (D3); the state check runs under the row lock (D5)."""
    product_id = await store.product_id_of(review_id)
    if product_id is None:
        raise ReviewNotFoundError(review_id)
    await products.lock(product_id)
    current = await store.lock_for_moderation(review_id)
    if current is None or current.deleted_at is not None:
        raise ReviewNotFoundError(review_id)
    if current.is_hidden is hide:
        raise ReviewModerationConflictError(current.is_hidden)
    hidden_at = now if hide else None
    await store.set_hidden(review_id, hidden=hide, at=now)
    await recompute_rating(store, products, product_id)
    await audit.record(
        actor_user_id=context.actor_user_id,
        action="review.hidden" if hide else "review.restored",
        entity_type=REVIEW_ENTITY_TYPE,
        entity_id=review_id,
        before_data=_state(current.is_hidden, current.hidden_at, product_id),
        after_data=_state(hide, hidden_at, product_id) | {"reason": reason},
        request_id=context.request_id,
        ip_hash=context.ip_hash,
    )
    return replace(current, is_hidden=hide, hidden_at=hidden_at)
