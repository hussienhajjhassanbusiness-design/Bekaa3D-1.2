from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Row, func, literal, select, tuple_, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.engagement.domain.entities import Notification
from app.engagement.domain.enums import NotificationType
from app.engagement.infrastructure.models import NotificationModel

# The column list used by every read path, so a RETURNING row and a SELECT row
# map through the same code.
_COLUMNS = (
    NotificationModel.id,
    NotificationModel.user_id,
    NotificationModel.type,
    NotificationModel.payload,
    NotificationModel.read_at,
    NotificationModel.created_at,
)


def _row_to_domain(row: Row[Any]) -> Notification:
    return Notification(
        id=row.id,
        user_id=row.user_id,
        type=row.type,
        payload=row.payload,
        read_at=row.read_at,
        created_at=row.created_at,
    )


def _model_to_domain(model: NotificationModel) -> Notification:
    return Notification(
        id=model.id,
        user_id=model.user_id,
        type=model.type,
        payload=model.payload,
        read_at=model.read_at,
        created_at=model.created_at,
    )


class NotificationRepository:
    """Persistence for the Notification aggregate.

    Internal to the Engagement context. Other contexts must not import this -
    they call `create_notification`, which is the sanctioned write port.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        user_id: UUID,
        notification_type: NotificationType,
        payload: dict[str, Any],
    ) -> Notification:
        """Insert and flush. Deliberately does not commit - see
        `create_notification` for why the caller owns the transaction."""
        model = NotificationModel(user_id=user_id, type=notification_type, payload=payload)
        self._session.add(model)
        # Flush rather than commit: this populates the server-generated `id` and
        # `created_at` so the caller gets a complete entity back, while leaving
        # the transaction open for whatever business change prompted it.
        await self._session.flush()
        await self._session.refresh(model)
        return _model_to_domain(model)

    async def list_page(
        self,
        *,
        user_id: UUID,
        limit: int,
        after: tuple[datetime, UUID] | None = None,
        read: bool | None = None,
    ) -> list[Notification]:
        """One page of a user's own notifications, newest first.

        Ownership is a predicate here rather than a check performed on the
        results: a filter that is part of the query cannot be forgotten on one
        branch the way an `if` after the fact can.
        """
        stmt = select(*_COLUMNS).where(NotificationModel.user_id == user_id)

        if read is True:
            stmt = stmt.where(NotificationModel.read_at.is_not(None))
        elif read is False:
            stmt = stmt.where(NotificationModel.read_at.is_(None))

        if after is not None:
            # Row-value comparison, which matches the index's own ordering and
            # so can be satisfied by a single range scan. The `id` half is not
            # decoration: `created_at` is not unique, and without a tie-breaker
            # two notifications sharing a timestamp straddle a page boundary -
            # one of them is served twice and the other never.
            after_created_at, after_id = after
            stmt = stmt.where(
                tuple_(NotificationModel.created_at, NotificationModel.id)
                < tuple_(
                    # Typed literals rather than bare values: asyncpg binds
                    # parameters with an explicit type, and an untyped datetime
                    # or UUID here is sent as text for PostgreSQL to guess at.
                    # Declaring them keeps the comparison on the same types the
                    # index is built over.
                    literal(after_created_at, DateTime(timezone=True)),
                    literal(after_id, postgresql.UUID(as_uuid=True)),
                )
            )

        stmt = stmt.order_by(
            NotificationModel.created_at.desc(), NotificationModel.id.desc()
        ).limit(limit)

        rows = (await self._session.execute(stmt)).all()
        return [_row_to_domain(row) for row in rows]

    async def set_read_state(
        self, *, notification_id: UUID, user_id: UUID, read: bool
    ) -> Notification | None:
        """Mark one of this user's notifications read or unread. `None` if there
        is no such notification *for this user*.

        A single atomic statement, with **no** `SELECT ... FOR UPDATE`. VS-007
        needed an explicit row lock because its update was a genuine
        read-modify-write whose audit row had to record a truthful
        `before -> after` chain; two unserialised administrators both read `10`
        and the log then claimed a transition that never happened. None of that
        applies here: this is idempotent state assignment, it computes nothing
        from the previous value, it writes no audit chain, and every interleaving
        of two concurrent calls leaves a legitimate state. The row lock
        PostgreSQL takes for the UPDATE itself is all the serialisation the
        statement needs.

        `COALESCE` is what makes marking read idempotent: `read_at` records when
        the notification was *first* read, so pressing the button twice must not
        move it. Marking unread is idempotent for the simpler reason that NULL
        assigned to NULL is a no-op.

        Ownership rides in the same WHERE clause as the id, so "not yours" and
        "does not exist" are indistinguishable to the caller by construction -
        there is no moment at which the row is in hand and a separate check
        could be skipped.
        """
        new_read_at = func.coalesce(NotificationModel.read_at, func.now()) if read else None
        stmt = (
            update(NotificationModel)
            .where(
                NotificationModel.id == notification_id,
                NotificationModel.user_id == user_id,
            )
            .values(read_at=new_read_at)
            .returning(*_COLUMNS)
            # The row is rebuilt from RETURNING rather than from the identity
            # map, so a stale instance loaded earlier in this session cannot be
            # what the response is rendered from.
            .execution_options(synchronize_session=False)
        )
        row = (await self._session.execute(stmt)).one_or_none()
        return _row_to_domain(row) if row is not None else None
