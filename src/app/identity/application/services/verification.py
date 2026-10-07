from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.identity.application.ports import VerificationTokenStore
from app.identity.application.security.token_service import generate_raw_token, hash_token
from app.identity.domain.entities import User
from app.platform.application.ports.outbox_writer import OutboxWriter

# V1 design assumptions (SRS §30.3 leaves token/session lifetimes to implementation
# time): a 24h verification window balances security against giving a real visitor
# enough time to act, and a 2min resend cooldown stops a single submit-mashing
# visitor from flooding their own inbox without needing full rate-limit infra here.
VERIFICATION_TOKEN_TTL = timedelta(hours=24)
RESEND_COOLDOWN = timedelta(minutes=2)


async def issue_verification_email(
    *,
    user: User,
    token_repo: VerificationTokenStore,
    outbox_repo: OutboxWriter,
) -> None:
    settings = get_settings()
    raw_token = generate_raw_token()
    expires_at = datetime.now(UTC) + VERIFICATION_TOKEN_TTL

    await token_repo.add(user_id=user.id, token_hash=hash_token(raw_token), expires_at=expires_at)
    await outbox_repo.add(
        user_id=user.id,
        recipient_email=user.email,
        template="verification_email",
        payload={
            "token": raw_token,
            # Frontend route, token in the fragment (BUG-09): it never reaches a
            # server log, and the frontend POSTs it to /api/v1/auth/verify-email.
            "verification_url": f"{settings.frontend_base_url}/verify-email#token={raw_token}",
            "expires_at": expires_at.isoformat(),
        },
    )


async def resend_eligible(*, user: User, token_repo: VerificationTokenStore) -> bool:
    if user.is_verified:
        return False
    latest = await token_repo.get_latest_for_user(user.id)
    if latest is None:
        return True
    return (datetime.now(UTC) - latest.created_at) >= RESEND_COOLDOWN
