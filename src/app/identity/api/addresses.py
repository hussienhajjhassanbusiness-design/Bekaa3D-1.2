"""The customer's address book (VS-026, F-025, FR-03). Reads need only a session; writes
need a verified email and CSRF. Another user's, a deleted and an unknown id give one 404."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.core.exceptions import ApiError
from app.identity.api.address_schemas import AddressCreate, AddressList, AddressRead, AddressUpdate
from app.identity.api.dependencies import (
    current_user,
    current_verified_user,
    not_found_error,
    require_csrf,
)
from app.identity.application.commands.address_book import (
    CreateAddress,
    DeleteAddress,
    SetDefaultAddress,
    UpdateAddress,
)
from app.identity.domain.address import AddressDetails
from app.identity.domain.entities import User
from app.identity.domain.exceptions import (
    AddressLimitReachedError,
    AddressNotFoundError,
    InvalidAddressError,
)
from app.identity.infrastructure.addresses import SqlAddressRepository

router = APIRouter(prefix="/me/addresses", tags=["addresses"])

_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session cookie was presented."},
}
_WRITE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_READ_RESPONSES,
    403: {"description": "CSRF token missing or invalid, or EMAIL_VERIFICATION_REQUIRED."},
}
_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"description": "No live address with this id belongs to the caller."}
}


def _invalid(exc: InvalidAddressError) -> RequestValidationError:
    return RequestValidationError(
        [
            {"loc": ("body", field), "msg": "invalid value", "type": "value_error"}
            for field in exc.fields
        ]
    )


@router.get(
    "", response_model=AddressList, summary="List my saved addresses", responses=_READ_RESPONSES
)
async def list_addresses(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> AddressList:
    rows = await SqlAddressRepository(session).list_live(user.id)
    return AddressList(items=[AddressRead.of(row) for row in rows])


@router.post(
    "",
    response_model=AddressRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    summary="Save a delivery address",
    responses={
        **_WRITE_RESPONSES,
        422: {"description": "Invalid field, or ADDRESS_LIMIT_REACHED; nothing is stored."},
    },
)
async def create_address(
    body: AddressCreate,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
) -> AddressRead:
    try:
        details = AddressDetails.of(**body.detail_values())
        address = await CreateAddress(SqlAddressRepository(session)).execute(
            user_id=user.id, details=details, make_default=body.is_default
        )
    except InvalidAddressError as exc:
        raise _invalid(exc) from exc
    except AddressLimitReachedError as exc:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="ADDRESS_LIMIT_REACHED",
            title="Address book is full",
            detail=f"At most {exc.limit} addresses can be saved; delete one first.",
        ) from exc
    return AddressRead.of(address)


@router.get(
    "/{address_id}",
    response_model=AddressRead,
    summary="Read one of my saved addresses",
    responses={**_READ_RESPONSES, **_NOT_FOUND},
)
async def read_address(
    address_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> AddressRead:
    address = await SqlAddressRepository(session).get_live(address_id=address_id, user_id=user.id)
    if address is None:
        raise not_found_error()
    return AddressRead.of(address)


@router.patch(
    "/{address_id}",
    response_model=AddressRead,
    dependencies=[Depends(require_csrf)],
    summary="Edit a saved address; past orders keep their own snapshot",
    responses={
        **_WRITE_RESPONSES,
        **_NOT_FOUND,
        422: {"description": "Empty body or invalid field."},
    },
)
async def update_address(
    address_id: UUID,
    body: AddressUpdate,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
) -> AddressRead:
    try:
        address = await UpdateAddress(SqlAddressRepository(session)).execute(
            user_id=user.id,
            address_id=address_id,
            changes=body.changes(),
            make_default=body.is_default,
        )
    except AddressNotFoundError as exc:
        raise not_found_error() from exc
    except InvalidAddressError as exc:
        raise _invalid(exc) from exc
    return AddressRead.of(address)


@router.delete(
    "/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(require_csrf)],
    summary="Delete a saved address (soft); deleting the default leaves no default",
    responses={**_WRITE_RESPONSES, **_NOT_FOUND},
)
async def delete_address(
    address_id: UUID,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await DeleteAddress(SqlAddressRepository(session)).execute(
            user_id=user.id, address_id=address_id
        )
    except AddressNotFoundError as exc:
        raise not_found_error() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{address_id}/default",
    response_model=AddressRead,
    dependencies=[Depends(require_csrf)],
    summary="Make this my default address; the previous default is cleared atomically",
    responses={**_WRITE_RESPONSES, **_NOT_FOUND},
)
async def set_default_address(
    address_id: UUID,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
) -> AddressRead:
    try:
        address = await SetDefaultAddress(SqlAddressRepository(session)).execute(
            user_id=user.id, address_id=address_id
        )
    except AddressNotFoundError as exc:
        raise not_found_error() from exc
    return AddressRead.of(address)
