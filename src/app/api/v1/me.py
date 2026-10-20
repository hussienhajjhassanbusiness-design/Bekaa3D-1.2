from fastapi import APIRouter

from app.engagement.api.notifications import router as engagement_notifications_router
from app.engagement.api.wishlist import router as engagement_wishlist_router
from app.identity.api.addresses import router as identity_addresses_router
from app.identity.api.profile import router as identity_profile_router
from app.negotiation.api.offers import router as negotiation_offers_router
from app.ordering.api.orders import router as ordering_orders_router
from app.ordering.api.ownership import router as ordering_ownership_router
from app.ordering.api.payment_retry import router as ordering_payment_retry_router

router = APIRouter()
router.include_router(identity_profile_router)
router.include_router(engagement_notifications_router)
router.include_router(identity_addresses_router)
router.include_router(engagement_wishlist_router)
router.include_router(ordering_ownership_router)
# VS-024: a new payment attempt for the caller's own unpaid order.
router.include_router(ordering_payment_retry_router)
router.include_router(ordering_orders_router)
router.include_router(negotiation_offers_router)
