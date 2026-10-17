"""Idempotency keys (SRS 7.5; VS-023 plan 3.7): what a claim can find, and the request
fingerprint. A claim is `in_progress` from the first transaction, `done` once stored."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

IDEMPOTENCY_TTL = timedelta(hours=24)
IN_PROGRESS = "in_progress"
DONE = "done"


@dataclass(frozen=True)
class NewClaim:
    record_id: UUID


@dataclass(frozen=True)
class Replay:
    status_code: int
    body: dict[str, Any]


@dataclass(frozen=True)
class InProgress:
    """The same request is still between its transactions, or crashed there."""

    resource_id: UUID | None


@dataclass(frozen=True)
class Conflict:
    """The key was used for a different request body."""


Claim = NewClaim | Replay | InProgress | Conflict


def request_hash(scope: str, body: Mapping[str, Any]) -> str:
    """SHA-256 of the scope and the canonical JSON body: key order and spacing ignored."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(f"{scope}\n{canonical}".encode()).hexdigest()
