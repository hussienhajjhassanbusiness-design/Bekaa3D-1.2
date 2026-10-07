"""Issuing password-reset tokens and deciding when a new one is allowed.

Deliberately parallel to services/verification.py rather than shared with it.
The two flows look alike but authorise different things - a verification token
proves control of a mailbox, a reset token replaces a credential - and folding
them into one helper would make it easy to give them one lifetime, one cooldown
and eventually one token table."""

from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.identity.application.ports import PasswordResetTokenStore
from app.identity.application.security.token_service import generate_raw_token, hash_token
from app.identity.domain.entities import User
from app.platform.application.ports.outbox_writer import OutboxWriter

# V1 design assumptions (SRS §30.3 leaves token lifetimes to implementation
# time). One hour, not the 24h a verification token gets: this token authorises
# taking over an account, so the window in which a leaked or forwarded email is
# still redeemable should be as short as a real person needs to act. The 2min
# cooldown matches RESEND_COOLDOWN and exists for the same reason - to stop one
# submit-mashing visitor flooding a mailbox.
PASSWORD_RESET_TOKEN_TTL = timedelta(hours=1)
RESET_REQUEST_COOLDOWN = timedelta(minutes=2)


async def issue_password_reset_email(
    *,
    user: User,
    token_repo: PasswordResetTokenStore,
    outbox_repo: OutboxWriter,
) -> None:
    settings = get_settings()
    raw_token = generate_raw_token()
    expires_at = datetime.now(UTC) + PASSWORD_RESET_TOKEN_TTL

    # Only the hash is persisted. The raw token exists in this function, in the
    # outbox payload, and in the user's inbox - nowhere else.
    await token_repo.add(user_id=user.id, token_hash=hash_token(raw_token), expires_at=expires_at)
    await outbox_repo.add(
        user_id=user.id,
        recipient_email=user.email,
        template="password_reset_email",
        payload={
            "token": raw_token,
            # Frontend route, token in the fragment (BUG-09): the reset page
            # collects the new password and POSTs both to
            # /api/v1/auth/password-reset/confirm, which stays POST-only.
            "reset_url": f"{settings.frontend_base_url}/reset-password#token={raw_token}",
            "expires_at": expires_at.isoformat(),
        },
    )


async def reset_request_eligible(*, user: User, token_repo: PasswordResetTokenStore) -> bool:
    """Whether this account should be sent a reset email right now.

    Unverified accounts are eligible: redeeming the token proves control of the
    mailbox, which is the same thing verification proves. Deactivated,
    anonymised and deleted accounts are not - there is nothing to recover."""
    if not user.can_authenticate:
        return False
    latest = await token_repo.get_latest_for_user(user.id)
    if latest is None:
        return True
    return (datetime.now(UTC) - latest.created_at) >= RESET_REQUEST_COOLDOWN
