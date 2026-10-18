"""The mock provider (VS-023 plan 3.6, Q15). State lives in Redis, shared by the API and
the worker; only `simulate()` changes it, and no HTTP route calls `simulate()`."""

import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote
from uuid import UUID

import redis.asyncio as redis

from app.payments.application.ports import (
    CreatedPayment,
    CreatePayment,
    ParsedEvent,
    PaymentRef,
    ProviderStatus,
)
from app.payments.domain.exceptions import (
    InvalidSignatureError,
    MalformedEventError,
    ProviderUnavailableError,
)
from app.payments.domain.limits import MOCK_REDIS_TIMEOUT_SECONDS, MOCK_STATE_TTL_SECONDS
from app.payments.domain.outcome import ProviderResult, ProviderState

SIGNATURE_HEADER = "x-mock-signature"
STATE_TTL_SECONDS = MOCK_STATE_TTL_SECONDS
TIMEOUT_SECONDS = MOCK_REDIS_TIMEOUT_SECONDS
_STATES = frozenset({"pending", "processing", "paid", "failed", "expired"})


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _key(payment_id: UUID) -> str:
    return f"mock_payment:{payment_id}"


class MockPaymentProvider:
    name = "mock"
    supports_status_query = True

    def __init__(self, *, redis_url: str, webhook_secret: str, frontend_base_url: str) -> None:
        self._redis_url = redis_url
        self._secret = webhook_secret
        self._frontend = frontend_base_url.rstrip("/")
        self._client: redis.Redis | None = None

    def _redis(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(  # type: ignore[no-untyped-call]
                self._redis_url,
                socket_connect_timeout=TIMEOUT_SECONDS,
                socket_timeout=TIMEOUT_SECONDS,
                decode_responses=True,
            )
        return self._client

    async def _read(self, payment_id: UUID) -> dict[str, str]:
        # redis-py types hash commands as sync-or-async; this client is async.
        state: dict[str, str] = await self._redis().hgetall(_key(payment_id))  # type: ignore[misc]
        return state

    async def create_payment(self, request: CreatePayment) -> CreatedPayment:
        reference = f"mock_{secrets.token_hex(12)}"
        state = {
            "status": "pending",
            "amount_cents": str(request.amount_cents),
            "currency": request.currency,
            "provider_payment_id": reference,
        }
        try:
            async with self._redis().pipeline(transaction=True) as pipe:
                pipe.hset(_key(request.payment_id), mapping=state)
                pipe.expire(_key(request.payment_id), STATE_TTL_SECONDS)
                await pipe.execute()
        except redis.RedisError as exc:
            raise ProviderUnavailableError("mock state store unavailable") from exc
        return CreatedPayment(
            provider_payment_id=reference,
            redirect_url=f"{self._frontend}/checkout/return?order={quote(request.order_number)}",
        )

    async def query_status(self, ref: PaymentRef) -> ProviderStatus:
        """Never created (or its state expired): `unknown`, which writes nothing (3.2a)."""
        try:
            state = await self._read(ref.payment_id)
        except redis.RedisError as exc:
            raise ProviderUnavailableError("mock state store unavailable") from exc
        if not state:
            return ProviderStatus(ProviderResult("unknown", None, None), None)
        captured = state.get("captured_amount_cents")
        return ProviderStatus(
            ProviderResult(
                _state(state["status"]),
                int(captured) if captured else None,
                state["currency"] if captured else None,
            ),
            state["provider_payment_id"],
        )

    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> ParsedEvent:
        given = {k.lower(): v for k, v in headers.items()}.get(SIGNATURE_HEADER, "")
        if not hmac.compare_digest(given.encode(), sign(self._secret, body).encode()):
            raise InvalidSignatureError("mock signature mismatch")
        try:
            payload: Any = json.loads(body)
            reference = payload.get("payment_reference")
            return ParsedEvent(
                event_id=str(payload["event_id"]),
                event_type=str(payload["type"]),
                payment_reference=UUID(reference) if reference else None,
                provider_payment_id=payload.get("provider_payment_id"),
                payload=payload,
            )
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise MalformedEventError("unreadable mock event") from exc

    async def simulate(
        self,
        payment_id: UUID,
        state: ProviderState,
        captured_amount_cents: int | None = None,
        *,
        currency: str | None = None,
    ) -> None:
        """Tests and `scripts/mock_pay.py` only. `paid` captures the full amount unless
        `captured_amount_cents` says otherwise (under- or overpayment). `unknown` is never
        stored: it is only the answer for a payment the mock has no state for."""
        if state not in _STATES:
            raise ValueError(f"mock state {state!r} cannot be simulated")
        current = await self._read(payment_id)
        if not current:
            raise LookupError(f"mock payment {payment_id} was never created")
        update: dict[str, str] = {"status": state}
        if state == "paid":
            amount = captured_amount_cents
            update["captured_amount_cents"] = str(
                amount if amount is not None else current["amount_cents"]
            )
            if currency is not None:
                update["currency"] = currency
        await self._redis().hset(_key(payment_id), mapping=update)  # type: ignore[misc]

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def _state(value: str) -> ProviderState:
    if value not in _STATES:
        raise ProviderUnavailableError(f"mock state {value!r} is unknown")
    return value  # type: ignore[return-value]
