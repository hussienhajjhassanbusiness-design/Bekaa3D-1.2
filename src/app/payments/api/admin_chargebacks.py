"""Admin chargebacks (VS-030 plan 2.5; ADR-042 d3-d5): record one (required `Idempotency-Key`),
list an order's, get one. Mounted on the admin router (admin, MFA); writes need CSRF and the
refunds' per-admin limit. Production stays on `PAYMENT_PROVIDER=none` until VS-032."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Self
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.api.text import MultilineStr, PlainStr
from app.core.exceptions import ApiError
from app.identity.public import (
    AccessTokenClaims,
    AdminBoundaryRoute,
    not_found_error,
    require_admin,
    require_csrf,
)
from app.payments.api.admin_refunds import (
    _DOMAIN,
    _READ_LIMIT,
    _RESPONSES,
    _WRITE,
    _WRITE_LIMIT,
    IdempotencyKey,
    _ctx,
    _idempotent,
    _integrity_alert,
    _translate,
)
from app.payments.application.services.chargebacks import record_chargeback
from app.payments.domain import limits
from app.payments.domain.enums import PaymentProvider
from app.payments.domain.exceptions import (
    ChargebackAllocationInvalidError,
    ChargebackDuplicateError,
    ChargebackItemsForbiddenError,
    ChargebackNotOnlineError,
    OrderTotalMismatchError,
)
from app.payments.domain.refunds import ItemFact
from app.payments.infrastructure.chargebacks import (
    ChargebackRow,
    chargeback_row,
    order_chargebacks,
)
from app.payments.infrastructure.refund_side import refund_deps

admin_router = APIRouter(tags=["admin"], route_class=AdminBoundaryRoute)

CREATE_SCOPE = "admin_chargeback_create"


class ChargebackItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_item_id: UUID
    amount_cents: Annotated[int, Field(gt=0, le=limits.REFUND_MAX_AMOUNT_CENTS)]


class ChargebackCreate(BaseModel):
    """`items` are the lines the bank's charge covers beyond the open refunds it absorbs."""

    model_config = ConfigDict(extra="forbid")

    payment_id: UUID
    provider_dispute_reference: Annotated[
        PlainStr, Field(min_length=1, max_length=limits.DISPUTE_REFERENCE_MAX)
    ]
    charged_cents: Annotated[int, Field(gt=0, le=limits.REFUND_MAX_AMOUNT_CENTS)]
    items: Annotated[
        list[ChargebackItemCreate], Field(default_factory=list, max_length=limits.REFUND_MAX_ITEMS)
    ]
    reason: Annotated[MultilineStr, Field(min_length=1, max_length=limits.REFUND_TEXT_MAX)]
    received_at: AwareDatetime

    @field_validator("items")
    @classmethod
    def _unique(cls, items: list[ChargebackItemCreate]) -> list[ChargebackItemCreate]:
        if len({item.order_item_id for item in items}) != len(items):
            raise ValueError("each order_item_id may appear once")
        return items


class ChargebackItemRead(BaseModel):
    order_item_id: UUID
    product_name: str
    amount_cents: int


class ChargebackDetail(BaseModel):
    """Never a phone, hash, address or the payment's provider reference."""

    id: UUID
    order_id: UUID
    order_number: str
    payment_id: UUID
    payment_provider: PaymentProvider
    provider_dispute_reference: str
    charged_cents: int
    applied_cents: int = Field(description="Absorbed open refunds plus the items' coverage.")
    excess_cents: int = Field(description="Beyond what was left to refund: alerted.")
    currency: str
    reason: str
    recorded_by: UUID
    received_at: datetime
    created_at: datetime
    items: list[ChargebackItemRead]

    @classmethod
    def of(cls, row: ChargebackRow) -> Self:
        fields = {k: v for k, v in vars(row).items() if k != "items"}
        return cls(**fields, items=[ChargebackItemRead(**vars(item)) for item in row.items])


def _refused(exc: Exception) -> ApiError | None:
    if isinstance(exc, ChargebackNotOnlineError):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="CHARGEBACK_NOT_ONLINE",
            title="Not an online payment",
            detail="A cash payment cannot be charged back.",
        )
    if isinstance(exc, ChargebackItemsForbiddenError):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="CHARGEBACK_ITEMS_FORBIDDEN",
            title="No lines on a late-captured attempt",
            detail="This attempt never paid a line, so its chargeback names none.",
        )
    if isinstance(exc, ChargebackDuplicateError):
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="CHARGEBACK_DUPLICATE",
            title="Chargeback already recorded",
            detail="This provider's dispute reference is already recorded.",
        )
    if isinstance(exc, ChargebackAllocationInvalidError):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="CHARGEBACK_ALLOCATION_INVALID",
            title="Items exceed the available balance",
            detail="An item exceeds its line's balance, or the items exceed the payment's "
            "balance or what was charged beyond the absorbed refunds.",
            extensions={
                "available": {
                    "lines": [
                        {"order_item_id": str(line_id), "balance_cents": cents}
                        for line_id, cents in sorted(exc.lines.items(), key=lambda p: str(p[0]))
                    ],
                    "payment_cents": exc.payment_cents,
                    "chargeable_cents": exc.chargeable_cents,
                }
            },
        )
    return None


_CHARGEBACK_ERRORS = (
    ChargebackNotOnlineError,
    ChargebackItemsForbiddenError,
    ChargebackDuplicateError,
    ChargebackAllocationInvalidError,
)


async def _in_transaction(
    request: Request, order_id: UUID, work: Callable[[AsyncSession], Awaitable[Response]]
) -> Response:
    """One transaction for the claim, the locks and every write; a refusal stores nothing."""
    async with request.app.state.db_session_factory() as session:
        try:
            async with session.begin():
                try:
                    return await work(session)
                except _CHARGEBACK_ERRORS as exc:
                    refusal = _refused(exc)
                    assert refusal is not None
                    raise refusal from exc
                except _DOMAIN as exc:
                    raise await _translate(session, exc, None) from exc
        except OrderTotalMismatchError as exc:
            raise await _integrity_alert(request, exc, order_id) from exc


async def _detail(session: AsyncSession, chargeback_id: UUID) -> dict[str, Any]:
    row = await chargeback_row(session, chargeback_id)
    assert row is not None
    return ChargebackDetail.of(row).model_dump(mode="json")


@admin_router.post(
    "/orders/{order_id}/chargebacks",
    status_code=status.HTTP_201_CREATED,
    response_model=ChargebackDetail,
    dependencies=[Depends(require_csrf), _WRITE_LIMIT],
    summary="Record a chargeback: it voids the payment's open refunds and absorbs them",
    responses={
        **_WRITE,
        409: {
            "description": "ORDER_NOT_PAID, CHARGEBACK_DUPLICATE, ORDER_TOTAL_MISMATCH, "
            "IDEMPOTENCY_KEY_CONFLICT, or IDEMPOTENCY_REQUEST_IN_PROGRESS."
        },
        422: {
            "description": "CHARGEBACK_NOT_ONLINE, CHARGEBACK_ITEMS_FORBIDDEN, "
            "CHARGEBACK_ALLOCATION_INVALID (with `available`), or VALIDATION_ERROR."
        },
    },
)
async def create_order_chargeback(
    order_id: UUID,
    body: ChargebackCreate,
    request: Request,
    idempotency_key: IdempotencyKey,
    claims: AccessTokenClaims = Depends(require_admin),
) -> Response:
    items = sorted(
        (ItemFact(i.order_item_id, i.amount_cents) for i in body.items),
        key=lambda item: str(item.order_item_id),
    )
    fingerprint = {
        "order_id": str(order_id),
        "payment_id": str(body.payment_id),
        "provider_dispute_reference": body.provider_dispute_reference,
        "charged_cents": body.charged_cents,
        "items": [[str(i.order_item_id), i.amount_cents] for i in items],
        "reason": body.reason,
        "received_at": body.received_at.astimezone(UTC).isoformat(),
    }

    async def work(session: AsyncSession) -> Response:
        async def write() -> UUID:
            outcome = await record_chargeback(
                refund_deps(session),
                order_id=order_id,
                payment_id=body.payment_id,
                dispute_reference=body.provider_dispute_reference,
                charged_cents=body.charged_cents,
                items=items,
                reason=body.reason,
                received_at=body.received_at,
                ctx=_ctx(request, claims),
                at=datetime.now(UTC),
            )
            return outcome.chargeback_id

        return await _idempotent(
            request,
            session,
            scope=CREATE_SCOPE,
            admin_id=claims.user_id,
            key=idempotency_key,
            body=fingerprint,
            write=write,
            detail=_detail,
        )

    return await _in_transaction(request, order_id, work)


@admin_router.get(
    "/orders/{order_id}/chargebacks",
    response_model=list[ChargebackDetail],
    dependencies=[_READ_LIMIT],
    summary="An order's chargebacks, oldest first (never in the obligations queue)",
    responses=_RESPONSES,
)
async def list_order_chargebacks(
    order_id: UUID, session: AsyncSession = Depends(get_session)
) -> list[ChargebackDetail]:
    found = await session.scalar(text("SELECT 1 FROM orders WHERE id = :o"), {"o": order_id})
    if found is None:
        raise not_found_error()
    return [ChargebackDetail.of(row) for row in await order_chargebacks(session, order_id)]


@admin_router.get(
    "/chargebacks/{chargeback_id}",
    response_model=ChargebackDetail,
    dependencies=[_READ_LIMIT],
    summary="One chargeback with its items",
    responses=_RESPONSES,
)
async def get_chargeback(
    chargeback_id: UUID, session: AsyncSession = Depends(get_session)
) -> ChargebackDetail:
    row = await chargeback_row(session, chargeback_id)
    if row is None:
        raise not_found_error()
    return ChargebackDetail.of(row)
