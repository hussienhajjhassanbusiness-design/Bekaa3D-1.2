"""`POST /api/v1/webhooks/payments/{provider}` (VS-023 plan 2.2; SRS 9.2). No cookies, no
CSRF. Checks run in order: configured provider (404), 64 KiB body (400), signature, then
the bucket that matches it, then storage. The request never changes a payment."""

import json
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, get_session
from app.core.exceptions import ApiError
from app.core.rate_limit import enforce_rate_limit
from app.payments.application.services.webhooks import receive_webhook
from app.payments.domain.enums import PaymentProvider
from app.payments.domain.exceptions import InvalidSignatureError, MalformedEventError
from app.payments.domain.limits import (
    WEBHOOK_MAX_BODY_BYTES,
    WEBHOOK_UNVERIFIED_LIMIT,
    WEBHOOK_VERIFIED_LIMIT,
    WEBHOOK_WINDOW_SECONDS,
)
from app.payments.infrastructure.payments import SqlPaymentStore
from app.payments.infrastructure.verification import verify_in_background
from app.payments.infrastructure.webhook_events import SqlWebhookEventStore

logger = structlog.get_logger()

router = APIRouter(prefix="/webhooks/payments", tags=["payments"])

MAX_BODY_BYTES = WEBHOOK_MAX_BODY_BYTES
UNVERIFIED_LIMIT, VERIFIED_LIMIT = WEBHOOK_UNVERIFIED_LIMIT, WEBHOOK_VERIFIED_LIMIT
WINDOW_SECONDS = WEBHOOK_WINDOW_SECONDS

_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "VALIDATION_ERROR: body over 64 KiB, or a signed body unreadable."},
    401: {"description": "WEBHOOK_SIGNATURE_INVALID: not stored."},
    404: {"description": "The provider is not configured here (never `cash`)."},
    429: {"description": "RATE_LIMITED: per IP for bad signatures, per provider otherwise."},
}


def _stored_size(payload: dict[str, Any]) -> int:
    """`jsonb::text` spacing, which `ck_webhook_events_payload_size` measures."""
    return len(json.dumps(payload, separators=(", ", ": "), ensure_ascii=False).encode())


class WebhookAck(BaseModel):
    received: bool


def _invalid(detail: str) -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="VALIDATION_ERROR",
        title="Webhook body refused",
        detail=detail,
    )


async def _bounded_body(request: Request) -> bytes:
    """Refuses a body over the cap without reading past it: no bucket is spent."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise _invalid("The body is larger than 64 KiB.")
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            raise _invalid("The body is larger than 64 KiB.")
    return bytes(body)


async def _spend(
    request: Request, response: Response, *, prefix: str, subject: str, limit: int
) -> None:
    await enforce_rate_limit(
        request,
        response,
        key_prefix=prefix,
        subject=subject,
        limit=limit,
        window_seconds=WINDOW_SECONDS,
    )


@router.post(
    "/{provider}",
    response_model=WebhookAck,
    summary="Receive a payment provider's event; verification happens after the 200",
    responses=_RESPONSES,
)
async def receive_payment_webhook(
    provider: str,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> WebhookAck:
    providers = request.app.state.payment_providers
    adapter = providers.get(provider)
    if adapter is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            title="Not Found",
            detail="Not Found",
        )
    body = await _bounded_body(request)
    unverified = {"prefix": "webhook-unverified", "subject": client_ip(request) or "unknown"}
    try:
        event = adapter.parse_webhook(request.headers, body)
    except InvalidSignatureError as exc:
        await _spend(request, response, **unverified, limit=UNVERIFIED_LIMIT)
        await logger.aerror("payment_webhook_bad_signature", provider=provider)
        raise ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="WEBHOOK_SIGNATURE_INVALID",
            title="Webhook signature invalid",
            detail="The webhook signature did not verify.",
        ) from exc
    except MalformedEventError as exc:
        await _spend(request, response, prefix="webhook", subject=provider, limit=VERIFIED_LIMIT)
        raise _invalid("The signed body is not a readable event.") from exc
    await _spend(request, response, prefix="webhook", subject=provider, limit=VERIFIED_LIMIT)
    if _stored_size(event.payload) > MAX_BODY_BYTES:
        raise _invalid("The event is larger than 64 KiB once stored.")
    event_id = await receive_webhook(
        payments=SqlPaymentStore(session),
        events=SqlWebhookEventStore(session),
        provider=PaymentProvider(provider),
        event=event,
        signature_valid=True,
        at=datetime.now(UTC),
    )
    if event_id is not None:
        # Runs after the response is sent, so after `get_session` has committed it.
        background.add_task(
            verify_in_background, request.app.state.db_session_factory, providers, event_id
        )
    return WebhookAck(received=True)
