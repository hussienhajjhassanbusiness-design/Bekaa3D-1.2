"""Problem responses shared by the cart, checkout, retry and offer checkout routes."""

from collections.abc import Sequence
from uuid import UUID

from fastapi import status

from app.core.exceptions import ApiError
from app.ordering.domain.exceptions import PaymentAlreadyActiveError


def already_owned_error(product_ids: Sequence[UUID]) -> ApiError:
    """409 PRODUCT_ALREADY_OWNED: owned, or held by another live order of this customer."""
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="PRODUCT_ALREADY_OWNED",
        title="STL already owned",
        detail="You already own this STL, or it is in another of your unpaid orders.",
        extensions={"product_ids": [str(p) for p in product_ids]},
    )


def payment_already_active_error(exc: PaymentAlreadyActiveError) -> ApiError:
    """409 PAYMENT_ALREADY_ACTIVE: the live attempt to resume (VS-024, VS-041)."""
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="PAYMENT_ALREADY_ACTIVE",
        title="A payment is already in progress",
        detail="This order already has a payment in progress. Resume it instead.",
        extensions={
            "payment_id": str(exc.payment_id) if exc.payment_id else None,
            "payment_status": exc.status,
            "redirect_url": exc.redirect_url,
        },
    )
