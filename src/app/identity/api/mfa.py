"""Administrator MFA endpoints (F-118, SEC-04).

These sit under `/auth` rather than `/admin` because they are how an
administrator *reaches* the admin boundary - requiring the boundary to use them
would be circular.

They split into two groups with genuinely different auth levels, and conflating
them would be a security bug:

- **Enrollment** (`/setup`, `/setup/confirm`) and **regeneration**
  (`/recovery-codes/regenerate`) run on an ordinary authenticated administrator
  session, so `current_claims`, `require_csrf` and the 404 information-hiding
  rule all apply. Non-administrators get 404 (SEC-10).
- **`/verify`** runs *before* any session exists, authenticated by the login
  challenge alone. None of the session-based guards can apply there; see the
  route's own docstring for what replaces them."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cookies import set_access_cookie, set_session_cookies
from app.api.dependencies import client_ip, get_session
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.core.rate_limit import rate_limiter
from app.core.security import hash_ip
from app.identity.api.dependencies import (
    not_found_error,
    require_admin,
    require_csrf,
    user_agent,
)
from app.identity.api.schemas import (
    MfaRecoveryCodesRead,
    MfaRecoveryRegenerateRequest,
    MfaSetupConfirmRequest,
    MfaSetupRead,
    MfaSetupRequest,
    MfaVerifyRequest,
)
from app.identity.application.commands.mfa_complete_login import CompleteMfaLogin
from app.identity.application.commands.mfa_confirm_setup import ConfirmMfaSetup
from app.identity.application.commands.mfa_regenerate_recovery_codes import RegenerateRecoveryCodes
from app.identity.application.commands.mfa_setup import MfaSetup
from app.identity.application.commands.mfa_verify import VerifyMfa
from app.identity.application.security.session_tokens import issue_access_token
from app.identity.application.services.mfa_session import MfaSessionStore
from app.identity.application.token_claims import AccessTokenClaims
from app.identity.domain.enums import UserRole
from app.identity.domain.exceptions import (
    AccountDisabledError,
    InvalidCredentialsError,
    InvalidMfaCodeError,
    InvalidRecoveryCodeError,
    MfaAlreadyEnabledError,
    MfaCodeReplayedError,
    MfaNotEnrolledError,
)
from app.identity.infrastructure.repositories import (
    MfaCredentialRepository,
    MfaRecoveryCodeRepository,
    SessionRepository,
    UserRepository,
)
from app.platform.public import SqlAuditWriter

router = APIRouter(prefix="/auth/mfa", tags=["auth"])

# V1 design assumptions (SRS §30.3 leaves the numbers to implementation time),
# following the convention set by the VS-002 limits in identity/api/auth.py.
#
# These are markedly tighter than the customer auth limits. A TOTP is six
# digits, so the entire keyspace is a million guesses - the limit, not the
# secret's length, is what makes online guessing hopeless. Enrollment is rarer
# still: an administrator enrols roughly once.
_MFA_SETUP_LIMIT = rate_limiter(key_prefix="auth:mfa:setup", limit=5, window_seconds=3600)
_MFA_CONFIRM_LIMIT = rate_limiter(key_prefix="auth:mfa:confirm", limit=10, window_seconds=3600)
_MFA_VERIFY_LIMIT = rate_limiter(key_prefix="auth:mfa:verify", limit=10, window_seconds=900)
_MFA_RECOVERY_LIMIT = rate_limiter(key_prefix="auth:mfa:recovery", limit=5, window_seconds=3600)


def _invalid_mfa_error() -> ApiError:
    """The single answer for every wrong second factor.

    Wrong TOTP, unknown recovery code and already-spent recovery code all land
    here. Distinguishing them would tell an attacker holding a stolen recovery
    sheet which entries were already used."""
    return ApiError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="MFA_INVALID",
        title="Second factor rejected",
        detail="The code provided is not valid.",
    )


async def require_admin_enrollment(
    claims: AccessTokenClaims = Depends(require_csrf),
) -> AccessTokenClaims:
    """Authenticated administrator, MFA *not* required.

    Distinct from `require_admin` on purpose: enrollment is how MFA gets set up
    in the first place, so demanding a completed second factor here would leave
    a newly created administrator permanently unable to enrol. Depends on
    `require_csrf` because every route below is an authenticated POST (SEC-03).

    Non-administrators still get 404 rather than 403 (SEC-10)."""
    if claims.role is not UserRole.ADMIN:
        raise not_found_error()
    return claims


@router.post(
    "/setup",
    response_model=MfaSetupRead,
    dependencies=[Depends(_MFA_SETUP_LIMIT)],
    summary="Begin TOTP enrollment",
    responses={
        401: {"description": "No valid session, or the password did not match."},
        404: {"description": "Caller is not an administrator."},
        409: {"description": "MFA is already enabled; enrollment cannot be restarted."},
        429: {"description": "Rate limit exceeded."},
    },
)
async def setup_mfa(
    body: MfaSetupRequest,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin_enrollment),
    session: AsyncSession = Depends(get_session),
) -> MfaSetupRead:
    """Returns the TOTP secret exactly once. MFA is *not* enabled by this call -
    `enabled_at` stays NULL until `/setup/confirm` proves the authenticator
    works."""
    use_case = MfaSetup(
        user_repo=UserRepository(session),
        credential_repo=MfaCredentialRepository(session),
        audit_writer=SqlAuditWriter(session),
    )
    ip = client_ip(request)
    try:
        result = await use_case.execute(
            user_id=claims.user_id,
            current_password=body.current_password,
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
    except MfaAlreadyEnabledError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVALID_STATE_TRANSITION",
            title="MFA is already enabled",
            detail="MFA is already enabled for this account and cannot be re-enrolled.",
        ) from exc
    except MfaNotEnrolledError as exc:
        raise not_found_error() from exc

    return MfaSetupRead(
        secret=result.secret,
        otpauth_uri=result.otpauth_uri,
        issuer=result.issuer,
        account_name=result.account_name,
    )


@router.post(
    "/setup/confirm",
    response_model=MfaRecoveryCodesRead,
    dependencies=[Depends(_MFA_CONFIRM_LIMIT)],
    summary="Confirm TOTP enrollment and enable MFA",
    responses={
        401: {"description": "No valid session."},
        404: {"description": "Caller is not an administrator."},
        409: {"description": "MFA is already enabled; confirmation cannot be repeated."},
        422: {"description": "The code did not match the enrolled secret."},
        429: {"description": "Rate limit exceeded."},
    },
)
async def confirm_mfa_setup(
    body: MfaSetupConfirmRequest,
    request: Request,
    response: Response,
    claims: AccessTokenClaims = Depends(require_admin_enrollment),
    session: AsyncSession = Depends(get_session),
) -> MfaRecoveryCodesRead:
    """Enables MFA and returns the one-time recovery codes.

    The current session also becomes MFA-complete: the administrator just
    demonstrated the factor, so making them immediately answer a challenge for
    the same secret would be ceremony without security."""
    use_case = ConfirmMfaSetup(
        credential_repo=MfaCredentialRepository(session),
        recovery_repo=MfaRecoveryCodeRepository(session),
        audit_writer=SqlAuditWriter(session),
    )
    ip = client_ip(request)
    try:
        result = await use_case.execute(
            user_id=claims.user_id,
            code=body.code,
            request_id=getattr(request.state, "request_id", None),
            ip_hash=hash_ip(ip) if ip else None,
        )
    except InvalidMfaCodeError as exc:
        # 422 here rather than the 401 used elsewhere: the contract says 422 for
        # this endpoint, and the caller's *session* is fine - it is the code
        # that failed.
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="MFA_INVALID",
            title="Second factor rejected",
            detail="The code provided does not match the enrolled secret.",
        ) from exc
    except MfaAlreadyEnabledError as exc:
        # Same answer `/setup` gives for the same reason. Confirmation is part
        # of enrollment and enrollment is over; repeating it would rotate the
        # recovery-code set without the password that route requires.
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVALID_STATE_TRANSITION",
            title="MFA is already enabled",
            detail="MFA is already enabled for this account and cannot be re-confirmed.",
        ) from exc
    except MfaNotEnrolledError as exc:
        raise not_found_error() from exc

    settings = get_settings()
    store = MfaSessionStore(request.app.state.redis)
    await store.mark_completed(
        session_id=claims.session_id, ttl_seconds=settings.refresh_token_days * 24 * 60 * 60
    )
    set_access_cookie(
        response,
        issue_access_token(
            user_id=claims.user_id,
            session_id=claims.session_id,
            role=claims.role,
            email_verified=claims.email_verified,
            now=datetime.now(UTC),
            mfa_completed=True,
            # Re-minting after regenerating recovery codes. `claims.auth_epoch`
            # was already checked against the account's current value by
            # `require_admin` on the way in, so carrying it forward keeps this
            # token exactly as valid as the one it replaces - and no more.
            auth_epoch=claims.auth_epoch,
        ),
    )
    return MfaRecoveryCodesRead(
        recovery_codes=result.recovery_codes, generated_at=result.generated_at
    )


@router.post(
    "/verify",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_MFA_VERIFY_LIMIT)],
    summary="Complete admin login with the second factor",
    responses={
        401: {"description": "`MFA_INVALID` - the code or recovery code was rejected."},
        403: {"description": "The account was deactivated after the password was accepted."},
        410: {"description": "The challenge is unknown, spent or expired."},
        429: {"description": "Rate limit exceeded."},
    },
)
async def verify_mfa(
    body: MfaVerifyRequest,
    request: Request,
    response: Response,
    agent: str | None = Depends(user_agent),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Completes the login that `POST /auth/login` left at a challenge, and
    sets the full auth + CSRF cookies (api-endpoints.md:270).

    Note what does *not* guard this route. There is no session cookie yet - that
    is the entire point of the login-gated flow - so `current_claims` cannot
    apply, and double-submit CSRF is not available either, since CSRF is
    defined against a session that does not exist. What authenticates the
    caller is the challenge id: 192 bits of randomness, single-use, expiring in
    five minutes, and issued only to someone who has already presented the
    correct password. The rate limiter above is what stands between that and
    the six-digit keyspace behind it.

    The challenge is consumed before the factor is checked, so a wrong code
    burns it and the administrator logs in again for a fresh one. That denies
    an attacker a five-minute window to sit and guess against."""
    store = MfaSessionStore(request.app.state.redis)

    pending = await store.take_login_challenge(body.challenge_id)
    # A challenge minted before the account's last password reset is dead
    # (SEC-08). Checked here, before the second factor is examined, purely so a
    # doomed challenge does not spend the administrator's current TOTP time-step
    # on the way to being refused - the replay guard would then reject their
    # legitimate retry for the rest of that step. This is not the authoritative
    # check: CompleteMfaLogin repeats it under the user row lock, which is what
    # actually closes the race against a reset committing mid-request.
    stale_epoch = pending is not None and pending.epoch != await UserRepository(
        session
    ).get_auth_epoch(pending.user_id)
    if pending is None or stale_epoch:
        raise ApiError(
            status_code=status.HTTP_410_GONE,
            code="RESOURCE_EXPIRED",
            title="Challenge expired",
            detail="This MFA challenge is no longer valid. Sign in again to obtain a new one.",
        )

    ip = client_ip(request)
    ip_hash = hash_ip(ip) if ip else None
    request_id = getattr(request.state, "request_id", None)

    verify = VerifyMfa(
        credential_repo=MfaCredentialRepository(session),
        recovery_repo=MfaRecoveryCodeRepository(session),
        audit_writer=SqlAuditWriter(session),
    )
    try:
        await verify.execute(
            # From the challenge, never from the request body: the caller does
            # not get to name the account they are completing login for.
            user_id=pending.user_id,
            code=body.code,
            recovery_code=body.recovery_code,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except MfaCodeReplayedError as exc:
        # Caught before InvalidMfaCodeError, which it subclasses. The request
        # must fail, but the `mfa.replay_rejected` row it just wrote has to
        # survive: get_session wraps the request in one transaction, so raising
        # straight through would roll the evidence back along with everything
        # else. Same pattern the refresh route uses for reuse detection.
        await session.commit()
        # Identical to any other rejected code. The audit row is internal; the
        # caller learns nothing about why.
        raise _invalid_mfa_error() from exc
    except (InvalidMfaCodeError, InvalidRecoveryCodeError) as exc:
        raise _invalid_mfa_error() from exc
    except MfaNotEnrolledError as exc:
        # Only reachable if the credential was disabled inside the challenge
        # window. Same answer as a wrong code - there is no caller who is
        # entitled to learn the difference at this point.
        raise _invalid_mfa_error() from exc

    complete = CompleteMfaLogin(
        user_repo=UserRepository(session),
        session_repo=SessionRepository(session),
        audit_writer=SqlAuditWriter(session),
    )
    try:
        result = await complete.execute(
            user_id=pending.user_id,
            # Carried from the challenge and re-checked under the user row lock:
            # a challenge minted before a password reset must not mint a session
            # after it (SEC-08).
            challenge_epoch=pending.epoch,
            ip_hash=ip_hash,
            user_agent=agent,
            request_id=request_id,
        )
    except InvalidCredentialsError as exc:
        raise _invalid_mfa_error() from exc
    except AccountDisabledError as exc:
        # Same wording VS-003's login uses, so an account deactivated between
        # the two halves of a login is reported identically either way.
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="ACCOUNT_DISABLED",
            title="Account unavailable",
            detail="This account can no longer be used to sign in.",
        ) from exc

    settings = get_settings()
    await store.mark_completed(
        session_id=result.session_id, ttl_seconds=settings.refresh_token_days * 24 * 60 * 60
    )
    set_session_cookies(
        response,
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        csrf_token=result.csrf_token,
    )


@router.post(
    "/recovery-codes/regenerate",
    response_model=MfaRecoveryCodesRead,
    dependencies=[Depends(_MFA_RECOVERY_LIMIT), Depends(require_csrf)],
    summary="Replace the unused recovery-code set",
    responses={
        401: {"description": "No valid session, MFA incomplete, or password mismatch."},
        404: {"description": "Caller is not an administrator."},
        429: {"description": "Rate limit exceeded."},
    },
)
async def regenerate_recovery_codes(
    body: MfaRecoveryRegenerateRequest,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> MfaRecoveryCodesRead:
    """Admin + MFA. Invalidates every unused code and issues a fresh set,
    returned once."""
    use_case = RegenerateRecoveryCodes(
        user_repo=UserRepository(session),
        credential_repo=MfaCredentialRepository(session),
        recovery_repo=MfaRecoveryCodeRepository(session),
        audit_writer=SqlAuditWriter(session),
    )
    ip = client_ip(request)
    try:
        result = await use_case.execute(
            user_id=claims.user_id,
            current_password=body.current_password,
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
    except MfaNotEnrolledError as exc:
        raise not_found_error() from exc

    return MfaRecoveryCodesRead(
        recovery_codes=result.recovery_codes, generated_at=result.generated_at
    )
