"""ADR-026: Turnstile refusals are the visitor's; every other failure is no verdict."""

import json
from collections.abc import Callable
from urllib.parse import parse_qs

import httpx
import pytest
from structlog.testing import capture_logs

from app.integrations.captcha.ports import CaptchaRefusedError, CaptchaUnavailableError
from app.integrations.captcha.turnstile import SITEVERIFY_URL, TurnstileCaptcha

TOKEN = "0.visitor-token-sentinel"


def _adapter(handler: Callable[[httpx.Request], httpx.Response]) -> TurnstileCaptcha:
    return TurnstileCaptcha("s3cret", transport=httpx.MockTransport(handler))


def _answer(body: object, status: int = 200) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _request: httpx.Response(status, json=body)


async def test_success_passes_and_posts_secret_and_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"success": True, "error-codes": []})

    await _adapter(handler).verify(TOKEN)
    assert str(seen[0].url) == SITEVERIFY_URL
    form = parse_qs(seen[0].content.decode())
    assert form == {"secret": ["s3cret"], "response": [TOKEN]}


@pytest.mark.parametrize(
    "codes",
    [
        ["invalid-input-response"],
        ["timeout-or-duplicate"],
        ["missing-input-response"],
        ["invalid-input-response", "timeout-or-duplicate"],
    ],
)
async def test_visitor_errors_are_refusals(codes: list[str]) -> None:
    with pytest.raises(CaptchaRefusedError):
        await _adapter(_answer({"success": False, "error-codes": codes})).verify(TOKEN)


async def test_empty_token_is_refused_without_calling_cloudflare() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"success": True})

    with pytest.raises(CaptchaRefusedError):
        await _adapter(handler).verify("")
    assert calls == []


def _raise(exc: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


@pytest.mark.parametrize(
    "handler",
    [
        _answer({"success": False, "error-codes": ["internal-error"]}),
        _answer({"success": False, "error-codes": ["invalid-input-secret"]}),
        _answer({"success": False, "error-codes": ["missing-input-secret"]}),
        _answer({"success": False, "error-codes": ["bad-request"]}),
        _answer({"success": False, "error-codes": ["invalid-input-response", "internal-error"]}),
        _answer({"success": False, "error-codes": ["some-future-code"]}),
        _answer({"success": False}),
        _answer({"success": "true"}),
        _answer(["success"]),
        _answer({"success": True}, status=500),
        _answer({"success": True}, status=403),
        lambda _request: httpx.Response(200, content=b"<html>not json</html>"),
        _raise(httpx.ConnectError("down")),
        _raise(httpx.ReadTimeout("slow")),
    ],
)
async def test_everything_else_is_unavailable(
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    with pytest.raises(CaptchaUnavailableError):
        await _adapter(handler).verify(TOKEN)


@pytest.mark.parametrize(
    "body",
    [
        {"success": False, "error-codes": ["invalid-input-secret"]},
        {"success": False, "error-codes": ["invalid-input-response"]},
    ],
)
async def test_neither_token_nor_secret_is_logged(body: object) -> None:
    with capture_logs() as logs, pytest.raises((CaptchaRefusedError, CaptchaUnavailableError)):
        await _adapter(_answer(body)).verify(TOKEN)
    dumped = json.dumps(logs, default=str)
    assert TOKEN not in dumped
    assert "s3cret" not in dumped
