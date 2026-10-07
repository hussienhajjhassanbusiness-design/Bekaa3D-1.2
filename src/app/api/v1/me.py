from fastapi import APIRouter

from app.engagement.api.notifications import router as engagement_notifications_router
from app.identity.api.profile import router as identity_profile_router

router = APIRouter()
router.include_router(identity_profile_router)
router.include_router(engagement_notifications_router)
