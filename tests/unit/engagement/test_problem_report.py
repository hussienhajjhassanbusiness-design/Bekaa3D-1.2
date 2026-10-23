"""A customer's problem report as a contact message, and who hears of it (VS-029b, ADR-041)."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from app.engagement.application.commands.submit_problem_report import SubmitProblemReport
from app.engagement.domain.contact_message import (
    MESSAGE_MAX,
    NAME_MAX,
    ContactDetails,
    ContactMessage,
    ProblemReport,
    problem_report_notification,
)
from app.engagement.domain.entities import Notification
from app.engagement.domain.enums import ContactMessageStatus, NotificationType
from app.engagement.domain.exceptions import InvalidContactDetailsError

ORDER, USER = uuid.uuid4(), uuid.uuid4()


def _report(**over: Any) -> ProblemReport:
    args: dict[str, Any] = {
        "user_id": USER,
        "order_id": ORDER,
        "order_number": "B3D-ABC123",
        "recipient_name": "Rana",
        "email": "rana.k@example.com",
        "message": "  The lamp is cracked.\n ",
    } | over
    return ProblemReport.of(**args)


def test_the_report_trims_the_message_and_names_the_order() -> None:
    report = _report()
    assert (report.name, report.message) == ("Rana", "The lamp is cracked.")
    assert report.subject == "Problem with order B3D-ABC123"


@pytest.mark.parametrize("recipient", [None, "", "   "])
def test_without_a_recipient_the_name_is_the_emails_local_part(recipient: str | None) -> None:
    assert _report(recipient_name=recipient).name == "rana.k"


def test_a_long_name_is_cut_to_the_column_limit() -> None:
    assert len(_report(recipient_name="x" * 300).name) == NAME_MAX


@pytest.mark.parametrize("message", ["", "  \n ", "y" * (MESSAGE_MAX + 1)])
def test_a_blank_or_over_long_message_is_refused(message: str) -> None:
    with pytest.raises(InvalidContactDetailsError):
        _report(message=message)


def test_the_notification_carries_ids_and_the_order_number_only() -> None:
    message_id = uuid.uuid4()
    assert problem_report_notification(_report(), message_id) == {
        "event": "order.problem_reported",
        "order_id": str(ORDER),
        "order_number": "B3D-ABC123",
        "contact_message_id": str(message_id),
        "title": "Problem reported on order B3D-ABC123",
    }


@dataclass
class FakeMessages:
    added: list[ProblemReport] = field(default_factory=list)

    async def add_problem_report(self, report: ProblemReport) -> ContactMessage:
        self.added.append(report)
        at = datetime.now(UTC)
        return ContactMessage(
            id=uuid.uuid4(),
            name=report.name,
            email=report.email,
            phone=None,
            subject=report.subject,
            message=report.message,
            status=ContactMessageStatus.NEW,
            created_at=at,
            updated_at=at,
            user_id=report.user_id,
            order_id=report.order_id,
        )

    async def add(self, details: ContactDetails) -> ContactMessage:  # pragma: no cover
        raise AssertionError("a problem report is not a contact-form message")


@dataclass
class FakeNotifications:
    sent: list[tuple[uuid.UUID, NotificationType, dict[str, Any]]] = field(default_factory=list)

    async def add(
        self, *, user_id: uuid.UUID, notification_type: NotificationType, payload: dict[str, Any]
    ) -> Notification:
        self.sent.append((user_id, notification_type, payload))
        return Notification(
            id=uuid.uuid4(),
            user_id=user_id,
            type=notification_type,
            payload=payload,
            read_at=None,
            created_at=datetime.now(UTC),
        )


@dataclass
class FakeAdmins:
    ids: list[uuid.UUID]

    async def active_administrator_ids(self) -> list[uuid.UUID]:
        return self.ids


async def test_every_active_administrator_is_notified_once_after_the_message() -> None:
    admins = [uuid.uuid4(), uuid.uuid4()]
    messages, notifications = FakeMessages(), FakeNotifications()
    command = SubmitProblemReport(messages, notifications, FakeAdmins(admins))  # type: ignore[arg-type]
    message = await command.execute(_report())
    assert len(messages.added) == 1
    assert [user for user, _, _ in notifications.sent] == admins
    assert {kind for _, kind, _ in notifications.sent} == {NotificationType.ORDER}
    assert all(p["contact_message_id"] == str(message.id) for _, _, p in notifications.sent)


async def test_with_no_administrator_the_message_is_still_queued() -> None:
    messages, notifications = FakeMessages(), FakeNotifications()
    command = SubmitProblemReport(messages, notifications, FakeAdmins([]))  # type: ignore[arg-type]
    await command.execute(_report())
    assert (len(messages.added), notifications.sent) == (1, [])
