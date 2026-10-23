from app.engagement.application.ports import (
    AdministratorDirectory,
    ContactMessageStore,
    NotificationStore,
)
from app.engagement.application.services.notification_writer import write_notification
from app.engagement.domain.contact_message import (
    ContactMessage,
    ProblemReport,
    problem_report_notification,
)
from app.engagement.domain.enums import NotificationType


class SubmitProblemReport:
    """Queues the report and tells every active administrator, in the caller's transaction:
    unlike VS-034's, a failed notification fails the whole report (ADR-041 d4)."""

    def __init__(
        self,
        messages: ContactMessageStore,
        notifications: NotificationStore,
        administrators: AdministratorDirectory,
    ) -> None:
        self._messages = messages
        self._notifications = notifications
        self._administrators = administrators

    async def execute(self, report: ProblemReport) -> ContactMessage:
        message = await self._messages.add_problem_report(report)
        payload = problem_report_notification(report, message.id)
        for admin_id in await self._administrators.active_administrator_ids():
            await write_notification(
                self._notifications,
                user_id=admin_id,
                notification_type=NotificationType.ORDER,
                payload=payload,
            )
        return message
