"""The `manual` provider (ADR-049): the administrator arranges payment with the customer
and confirms it by hand. No outbound call, no status query and no webhooks."""

from collections.abc import Mapping

from app.payments.application.ports import (
    CreatedPayment,
    CreatePayment,
    ParsedEvent,
    PaymentRef,
    ProviderStatus,
)
from app.payments.domain.exceptions import InvalidSignatureError

NAME = "manual"


class ManualPaymentProvider:
    name = NAME
    supports_status_query = False
    accepts_webhooks = False

    async def create_payment(self, request: CreatePayment) -> CreatedPayment:
        return CreatedPayment(provider_payment_id=None, redirect_url=None)

    async def query_status(self, ref: PaymentRef) -> ProviderStatus:
        raise NotImplementedError("the manual provider is never asked (ADR-036 d5)")

    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> ParsedEvent:
        # Unreachable: the webhook route answers 404 for an adapter taking no webhooks.
        raise InvalidSignatureError("the manual provider sends no webhooks")

    async def aclose(self) -> None:
        return None
