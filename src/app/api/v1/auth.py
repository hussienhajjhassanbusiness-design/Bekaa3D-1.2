from fastapi import APIRouter

from app.identity.api.auth import router as identity_auth_router
from app.identity.api.mfa import router as identity_mfa_router

router = APIRouter()
router.include_router(identity_auth_router)
router.include_router(identity_mfa_router)
