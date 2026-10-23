"""`ProblemReportInbox` over Engagement's public surface, on the caller's session."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.engagement.public import ProblemReport, submit_problem_report


class EngagementProblemReportInbox:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def submit(
        self,
        *,
        user_id: UUID,
        order_id: UUID,
        order_number: str,
        recipient_name: str | None,
        email: str,
        message: str,
    ) -> UUID:
        report = ProblemReport.of(
            user_id=user_id,
            order_id=order_id,
            order_number=order_number,
            recipient_name=recipient_name,
            email=email,
            message=message,
        )
        return await submit_problem_report(self._session, report)
