"""Pay (or fail) a mock payment in local development: the only way to change mock state
outside the tests. Refuses production and the default secret outside development/test
(VS-023 plan 3.6); it needs direct Redis access, so no HTTP route can do this."""

import argparse
import asyncio
import json
import sys
import uuid

import httpx

from app.core.config import Settings, get_settings
from app.payments.infrastructure.providers.factory import configured_payment_providers
from app.payments.infrastructure.providers.mock import MockPaymentProvider, sign

STATES = ("paid", "processing", "failed", "expired")


class RefusedError(SystemExit):
    def __init__(self, reason: str) -> None:
        super().__init__(f"mock_pay refuses to run: {reason}")


def mock_provider(settings: Settings) -> MockPaymentProvider:
    """Boot's own allowlist decides: never production, never the default secret outside
    development and test, and only when PAYMENT_PROVIDER is mock."""
    try:
        provider = configured_payment_providers(settings).get("mock")
    except Exception as exc:
        raise RefusedError(str(exc)) from exc
    if not isinstance(provider, MockPaymentProvider):
        raise RefusedError("PAYMENT_PROVIDER is not mock")
    return provider


def signed_event(settings: Settings, payment_id: uuid.UUID) -> tuple[dict[str, str], bytes]:
    """A webhook naming the payment by our id only; verification asks the mock itself."""
    body = json.dumps(
        {
            "event_id": f"ev_{uuid.uuid4().hex}",
            "type": "payment.updated",
            "payment_reference": str(payment_id),
        }
    ).encode()
    headers = {
        "X-Mock-Signature": sign(settings.mock_webhook_secret, body),
        "Content-Type": "application/json",
    }
    return headers, body


async def run(
    payment_id: uuid.UUID,
    state: str,
    *,
    captured_amount_cents: int | None = None,
    send_to: str | None = None,
    settings: Settings | None = None,
) -> int | None:
    """Sets the mock state; with `send_to` (the API base URL) also posts the webhook."""
    settings = settings or get_settings()
    provider = mock_provider(settings)
    try:
        await provider.simulate(payment_id, state, captured_amount_cents)  # type: ignore[arg-type]
    finally:
        await provider.aclose()
    if send_to is None:
        return None
    headers, body = signed_event(settings, payment_id)
    async with httpx.AsyncClient(base_url=send_to, timeout=10) as client:
        response = await client.post(
            "/api/v1/webhooks/payments/mock", content=body, headers=headers
        )
    return response.status_code


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payment_id", type=uuid.UUID)
    parser.add_argument("state", choices=STATES)
    parser.add_argument("--captured-amount-cents", type=int, default=None)
    parser.add_argument("--send-to", default=None, help="API base URL, e.g. http://localhost:8000")
    arguments = parser.parse_args()
    status = asyncio.run(
        run(
            arguments.payment_id,
            arguments.state,
            captured_amount_cents=arguments.captured_amount_cents,
            send_to=arguments.send_to,
        )
    )
    print(f"mock payment {arguments.payment_id} -> {arguments.state}")
    if status is not None:
        print(f"webhook answered {status}")
        sys.exit(0 if status == 200 else 1)


if __name__ == "__main__":
    main()
