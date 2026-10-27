"""Engagement's published surface for other bounded contexts.

Another context may import from here or from `app.engagement.application.ports`,
and from nowhere else in Engagement (enforced by
`tests/unit/test_deep_architecture.py`).
"""

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.public import reviewable_products
from app.engagement.application.commands.purge_expired_attachments import (
    PurgeExpiredAttachments,
)
from app.engagement.application.commands.submit_problem_report import SubmitProblemReport
from app.engagement.application.ports import PurchaseEvidence
from app.engagement.application.services.notification_writer import write_notification
from app.engagement.application.services.reviews import recompute_rating
from app.engagement.domain.contact_message import MESSAGE_MAX, ProblemReport
from app.engagement.domain.entities import Notification
from app.engagement.domain.enums import NotificationType
from app.engagement.domain.reviews import Review, badge_shown
from app.engagement.infrastructure.administrators import IdentityAdministratorDirectory
from app.engagement.infrastructure.contact_messages import SqlContactMessageRepository
from app.engagement.infrastructure.custom_requests import SqlCustomRequestRepository
from app.engagement.infrastructure.repositories import NotificationRepository
from app.engagement.infrastructure.reviews import CatalogReviewableProducts, SqlReviewStore
from app.integrations.storage.ports import StoragePort

__all__ = [
    "PROBLEM_REPORT_MESSAGE_MAX",
    "NotificationType",
    "ProblemReport",
    "PurchaseEvidence",
    "ReviewRow",
    "create_notification",
    "lock_review_for_moderation",
    "purge_expired_attachments_batch",
    "recompute_product_rating",
    "referenced_attachment_keys",
    "refresh_review_badges",
    "reviews_for_export",
    "set_review_hidden",
    "submit_problem_report",
]

PROBLEM_REPORT_MESSAGE_MAX = MESSAGE_MAX
# VS-036 plan 3.6: the row VS-037 and VS-044 read.
ReviewRow = Review


async def create_notification(
    session: AsyncSession,
    *,
    user_id: UUID,
    notification_type: NotificationType,
    payload: dict[str, Any],
) -> Notification:
    """Validate and insert one notification. Does **not** commit.

    The caller's `AsyncSession` is taken as an argument rather than opened here,
    which is the same shape VS-007's settings reader uses and it is the whole
    point of the port. A business event and the notification announcing it land
    in one transaction:

        business mutation
        create_notification(...)
        email outbox insert, if the event also warrants email
        COMMIT

    So if the payment rolls back, the notification announcing it rolls back
    with it, and no customer is ever told about something that did not happen.
    A service that opened its own session and committed could not offer that -
    it would commit the announcement of a change that was still able to fail.

    There is no message broker, no event bus and no background notification
    worker. An in-app notification is a row; once the transaction commits it is
    already delivered, because "delivery" here is the customer reading their own
    table. That is what distinguishes it from email, which leaves the system.
    """
    return await write_notification(
        NotificationRepository(session),
        user_id=user_id,
        notification_type=notification_type,
        payload=payload,
    )


async def purge_expired_attachments_batch(
    session: AsyncSession, storage: StoragePort, *, now: datetime, limit: int
) -> int:
    """One `purge_expired_attachments` batch in the caller's transaction (VS-034)."""
    return await PurgeExpiredAttachments(
        SqlCustomRequestRepository(session), storage
    ).execute_batch(now=now, limit=limit)


async def referenced_attachment_keys(session: AsyncSession, keys: Sequence[str]) -> set[str]:
    """Which private attachment keys a row still names, for `reap_orphan_files`."""
    return await SqlCustomRequestRepository(session).referenced_keys(keys)


async def submit_problem_report(session: AsyncSession, report: ProblemReport) -> UUID:
    """The linked contact message plus one notification per active administrator, in the
    caller's transaction (VS-029b). Returns the message id. Does **not** commit."""
    message = await SubmitProblemReport(
        SqlContactMessageRepository(session),
        NotificationRepository(session),
        IdentityAdministratorDirectory(session),
    ).execute(report)
    return message.id


async def refresh_review_badges(
    session: AsyncSession,
    *,
    user_id: UUID,
    product_ids: Sequence[UUID],
    evidence: PurchaseEvidence,
) -> None:
    """Ordering's line writers only (VS-036 plan 3.2b): `R_user`, the live reviews FOR UPDATE
    by id, then the stored badge set from current evidence. Never products or aggregates."""
    if not product_ids:
        return
    store = SqlReviewStore(session)
    await store.lock_user(user_id)
    found = await store.lock_live_for_products(user_id, sorted(set(product_ids)))
    if not found:
        return
    true_ids = await evidence(user_id, sorted({product_id for _, product_id in found}))
    await store.set_verified([review_id for review_id, _ in found], true_ids)


async def recompute_product_rating(session: AsyncSession, product_id: UUID) -> None:
    """VS-037 after hide / restore; the caller already holds `lock_product_for_reviews`."""
    await recompute_rating(SqlReviewStore(session), CatalogReviewableProducts(session), product_id)


async def lock_review_for_moderation(session: AsyncSession, review_id: UUID) -> ReviewRow | None:
    """FOR UPDATE, after the product lock (VS-036 plan 8.1). The stored badge, unmasked.
    Deleted rows are returned too: the caller checks `deleted_at` (VS-037 d22)."""
    return await SqlReviewStore(session).lock_for_moderation(review_id)


async def set_review_hidden(
    session: AsyncSession, review_id: UUID, *, hidden: bool, at: datetime
) -> None:
    """VS-037: `is_hidden` and `hidden_at` together (ck_reviews_hidden_shape)."""
    await SqlReviewStore(session).set_hidden(review_id, hidden=hidden, at=at)


async def reviews_for_export(session: AsyncSession, user_id: UUID) -> list[ReviewRow]:
    """VS-044: every row, deleted and hidden included, the badge masked by D14."""
    rows = await SqlReviewStore(session).all_for_user(user_id)
    products = await reviewable_products(session, [row.product_id for row in rows])
    return [
        replace(
            row,
            is_verified_purchase=badge_shown(
                row.is_verified_purchase,
                products[row.product_id].purchase_mode if row.product_id in products else None,
            ),
        )
        for row in rows
    ]
