"""`adjust_wishlist_count` runs in the caller's transaction and never commits
(VS-038 plan §3) - the same contract as `app.engagement.public.create_notification`.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

from app.catalog.public import adjust_wishlist_count


async def test_adjust_wishlist_count_executes_once_and_never_commits() -> None:
    session = AsyncMock()

    await adjust_wishlist_count(session, uuid4(), 1)

    session.execute.assert_awaited_once()
    session.commit.assert_not_awaited()
