class EngagementDomainError(Exception):
    """Base for engagement-context domain errors. No HTTP knowledge lives here -
    routers translate these into the SRS-defined stable error codes."""


class InvalidNotificationPayloadError(EngagementDomainError):
    """A notification payload does not satisfy the contract.

    Carries the reasons as a list for the same reason `InvalidSettingValueError`
    does: one payload can break more than one rule at once (not an object *and*
    oversized is impossible, but a missing `event` *and* oversized is not), and
    a caller fixing it should see all of them at once.

    Raised by the writer service, so it is reachable only by our own code -
    there is no endpoint through which a customer submits a payload. That makes
    it a programming fault rather than a user error, and it is deliberately not
    mapped to a 4xx anywhere.
    """

    def __init__(self, reasons: list[str]) -> None:
        super().__init__(f"Notification payload is invalid: {'; '.join(reasons)}")
        self.reasons = reasons


class NotificationNotFoundError(EngagementDomainError):
    """No notification with this id belongs to this user.

    One error for two cases on purpose - the row does not exist, or it exists
    and belongs to someone else. The API answers both with the same 404, so the
    distinction must not survive as far as the router or it would eventually
    leak into a message.
    """

    def __init__(self, notification_id: object) -> None:
        super().__init__(f"No notification {notification_id!r} belongs to this user.")
        self.notification_id = notification_id
