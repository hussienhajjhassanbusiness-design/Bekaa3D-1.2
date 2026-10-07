from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.me import router as me_router
from app.catalog.api.reference_data import public_router as public_catalogue_router
from app.platform.api.settings import public_router as public_settings_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(admin_router)
router.include_router(me_router)
# Unauthenticated, and mounted at the version root rather than under /admin:
# GET /api/v1/settings/public is a public endpoint (api-endpoints.md:230).
router.include_router(public_settings_router)
# VS-010. Unauthenticated, rate-limited reference lists at the version root:
# GET /api/v1/{categories,materials,colours} (api-endpoints.md:227-229).
router.include_router(public_catalogue_router)
