"""Replaying an idempotent request's stored answer (VS-023 checkout, VS-024 retry; ADR-032
d7). Only a 201 and the post-commit 502 are stored; replays carry `Idempotent-Replayed`."""

import json
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.api.errors import problem_response
from app.platform.public import Replay

REPLAYED_HEADER = "Idempotent-Replayed"
_UNSTORED = ("instance", "request_id")
_PROBLEM_FIELDS = {"type", "title", "status", "detail", "instance", "code", "request_id", "errors"}


def replay(request: Request, record: Replay) -> Response:
    headers = {REPLAYED_HEADER: "true"}
    if record.status_code < 400:
        return JSONResponse(record.body, status_code=record.status_code, headers=headers)
    body = record.body
    return problem_response(
        request,
        status_code=record.status_code,
        code=body["code"],
        title=body["title"],
        detail=body["detail"],
        errors=body["errors"],
        headers=headers,
        extensions={k: v for k, v in body.items() if k not in _PROBLEM_FIELDS},
    )


def stored(response: JSONResponse) -> dict[str, Any]:
    """The problem body without what differs per request (instance, request id)."""
    body: dict[str, Any] = json.loads(bytes(response.body))
    return {k: v for k, v in body.items() if k not in _UNSTORED}
