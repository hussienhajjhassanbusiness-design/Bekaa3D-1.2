from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.me import router as me_router
from app.catalog.api.reference_data import public_router as public_catalogue_router
from app.catalog.api.search import public_router as search_router
from app.catalog.api.storefront import public_router as storefront_router
from app.engagement.api.contact_messages import public_router as contact_router
from app.engagement.api.custom_requests import public_router as custom_request_router
from app.ordering.api.cart import router as cart_router
from app.ordering.api.checkout import router as checkout_router
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
# VS-015. The public catalogue: GET /api/v1/products and /products/{slug}.
router.include_router(storefront_router)
# VS-016. Autocomplete: GET /api/v1/search/suggestions (search itself is `q` above).
router.include_router(search_router)
# VS-033. Guest contact form: captcha + rate limits, no auth cookies (api-endpoints.md 7.2).
router.include_router(contact_router)
# VS-022. The customer's cart: GET /api/v1/cart and /cart/items* (api-endpoints.md 10.1).
router.include_router(cart_router)
# VS-023. Checkout: POST /api/v1/checkout (two transactions; api-endpoints.md 10.2).
router.include_router(checkout_router)
# VS-034. Bring Your Idea: guest multipart form, captcha + rate limits (api-endpoints.md 7.2).
router.include_router(custom_request_router)
