"""Problem responses shared by the cart and checkout routes (VS-023)."""

from collections.abc import Sequence
from uuid import UUID

from fastapi import status

from app.core.exceptions import ApiError


def already_owned_error(product_ids: Sequence[UUID]) -> ApiError:
    """409 PRODUCT_ALREADY_OWNED: owned, or held by another live order of this customer."""
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="PRODUCT_ALREADY_OWNED",
        title="STL already owned",
        detail="You already own this STL, or it is in another of your unpaid orders.",
        extensions={"product_ids": [str(p) for p in product_ids]},
    )
