"""`GET /api/v1/me/stl-ownership` (VS-023 plan 2.3). A read: a session is enough, no
verified email and no rate limit, like `GET /cart`."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.catalog.application.ports import CartProductReader
from app.catalog.public import cart_product_reader
from app.identity.public import User, current_user
from app.ordering.application.services.ownership import owns_listed_stl
from app.ordering.infrastructure.orders import SqlOrderStore

router = APIRouter(prefix="/me/stl-ownership", tags=["checkout"])

_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session cookie was presented."},
}


class StlOwnershipRead(BaseModel):
    product_id: UUID
    owned: bool


@router.get(
    "",
    response_model=StlOwnershipRead,
    summary="Whether the caller owns this STL (paid and not refunded)",
    responses=_RESPONSES,
)
async def get_stl_ownership(
    product_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    products: CartProductReader = Depends(cart_product_reader),
) -> StlOwnershipRead:
    owned = await owns_listed_stl(
        products, SqlOrderStore(session), user_id=user.id, product_id=product_id
    )
    return StlOwnershipRead(product_id=product_id, owned=owned)
