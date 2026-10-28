from typing import Final

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cookies import clear_session_cookies
from app.api.dependencies import client_ip, get_session
from app.core.exceptions import ApiError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import hash_ip
from app.identity.api.dependencies import (
    current_user,
    current_verified_user,
    require_csrf,
    unauthenticated_error,
)
from app.identity.api.schemas import AccountDeletionRequest, UserProfileRead
from app.identity.application.commands.delete_account import DeleteAccount
from app.identity.domain.entities import User
from app.identity.domain.exceptions import (
    AccountDeletionBlockedError,
    AccountDisabledError,
    InvalidCredentialsError,
)
from app.identity.infrastructure.account_erasure import SqlAccountErasure
from app.identity.infrastructure.addresses import SqlAddressRepository
from app.identity.infrastructure.repositories import (
    PasswordResetTokenRepository,
    SessionRepository,
    UserRepository,
    VerificationTokenRepository,
)
from app.platform.public import SqlAuditWriter

DELETION_RATE_LIMIT: Final = 5
DELETION_RATE_WINDOW_SECONDS: Final = 3_600

router = APIRouter(prefix="/me", tags=["account"])


@router.get(
    "",
    response_model=UserProfileRead,
    summary="Read the authenticated user's own profile",
    responses={401: {"description": "No valid session cookie was presented."}},
)
async def read_profile(user: User = Depends(current_user)) -> UserProfileRead:
    """Ownership needs no check here: the subject is taken from the signed
    access token, so there is no identifier a caller could substitute for
    someone else's. V1 exposes no mutable profile field, so there is
    deliberately no counterpart write endpoint (api-endpoints.md 9.1)."""
    return UserProfileRead.from_user(user)


async def _deletion_rate_limit(
    request: Request, response: Response, user: User = Depends(current_verified_user)
) -> None:
    """Per user, after CSRF and the verified check: it bounds password guesses (ADR-047)."""
    await enforce_rate_limit(
        request,
        response,
        key_prefix="account_deletion",
        subject=str(user.id),
        limit=DELETION_RATE_LIMIT,
        window_seconds=DELETION_RATE_WINDOW_SECONDS,
    )


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf), Depends(_deletion_rate_limit)],
    summary="Delete the caller's account by anonymising it",
    responses={
        401: {"description": "AUTH_REQUIRED, or INVALID_CREDENTIALS: wrong current password."},
        403: {"description": "CSRF_INVALID, or EMAIL_VERIFICATION_REQUIRED."},
        409: {
            "description": "ACCOUNT_DELETION_BLOCKED; `reason` is open_order, "
            "unsettled_refund or administrator."
        },
        429: {"description": "RATE_LIMITED: five attempts an hour per user."},
    },
)
async def delete_my_account(
    body: AccountDeletionRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """All or nothing in the request's transaction (BR-125, BR-126, ADR-047); the cookies go."""
    ip = client_ip(request)
    try:
        await DeleteAccount(
            users=UserRepository(session),
            sessions=SessionRepository(session),
            addresses=SqlAddressRepository(session),
            verification_tokens=VerificationTokenRepository(session),
            reset_tokens=PasswordResetTokenRepository(session),
            erasure=SqlAccountErasure(session),
            audit=SqlAuditWriter(session),
        ).execute(
            user_id=user.id,
            password=body.current_password,
            request_id=getattr(request.state, "request_id", None),
            ip_hash=hash_ip(ip) if ip else None,
        )
    except InvalidCredentialsError as exc:
        raise ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_CREDENTIALS",
            title="Password incorrect",
            detail="The current password is incorrect.",
        ) from exc
    except AccountDisabledError as exc:
        raise unauthenticated_error() from exc
    except AccountDeletionBlockedError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="ACCOUNT_DELETION_BLOCKED",
            title="Account cannot be deleted yet",
            detail="Finish open orders and settle refunds before deleting the account.",
            extensions={"reason": exc.reason},
        ) from exc
    clear_session_cookies(response)
