"""VS-045: an abandoned outbox row is terminal and redacted, like any other failure."""

import uuid
from datetime import UTC, datetime

from app.platform.domain.entities import REDACTED, EmailOutboxMessage
from app.platform.domain.enums import OutboxStatus

AT = datetime(2026, 10, 28, tzinfo=UTC)


def test_abandon_fails_the_row_and_redacts_its_payload() -> None:
    message = EmailOutboxMessage(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        recipient_email="someone@example.com",
        template="order_placed",
        payload={"order_number": "BK-1", "token": "secret"},
        status=OutboxStatus.PENDING,
        send_after=AT,
        attempt_count=0,
        last_error=None,
        sent_at=None,
        created_at=AT,
        updated_at=AT,
    )
    message.abandon("account_deleted", at=AT)
    assert (message.status, message.last_error, message.sent_at) == (
        OutboxStatus.FAILED,
        "account_deleted",
        None,
    )
    assert message.payload == {"order_number": REDACTED, "token": REDACTED}
