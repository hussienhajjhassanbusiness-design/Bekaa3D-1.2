from fastapi import APIRouter, Depends

from app.identity.api.dependencies import current_user
from app.identity.api.schemas import UserProfileRead
from app.identity.domain.entities import User

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
