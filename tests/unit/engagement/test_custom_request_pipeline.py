"""VS-035 / BR-113, BR-114, SRS 20.7: the Bring Your Idea pipeline's edges and effects."""

import ast
import importlib
import itertools
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.engagement.domain.custom_request import (
    QUOTE_MAX_CENTS,
    QUOTE_MIN_CENTS,
    CustomRequestAttachment,
    check_quote,
    download_filename,
    is_expired,
    plan_transition,
)
from app.engagement.domain.enums import CustomRequestOutcome, CustomRequestStatus
from app.engagement.domain.exceptions import (
    InvalidCustomRequestTransitionError,
    InvalidQuoteError,
)

S = CustomRequestStatus
OUT = CustomRequestOutcome
LEGAL = {
    (S.NEW, S.CONTACTED),
    (S.CONTACTED, S.QUOTED),
    (S.CONTACTED, S.LOST),
    (S.QUOTED, S.IN_PROGRESS),
    (S.QUOTED, S.LOST),
    (S.IN_PROGRESS, S.COMPLETED),
    (S.COMPLETED, S.CLOSED),
}
ILLEGAL = sorted(set(itertools.product(S, S)) - LEGAL)


def _amount(target: CustomRequestStatus) -> int | None:
    return 12_500 if target is S.QUOTED else None


@pytest.mark.parametrize(("current", "target"), sorted(LEGAL))
def test_every_pipeline_edge_is_allowed(
    current: CustomRequestStatus, target: CustomRequestStatus
) -> None:
    assert plan_transition(current, target, _amount(target)).status is target


@pytest.mark.parametrize(("current", "target"), ILLEGAL)
def test_every_other_pair_is_refused_staying_put_included(
    current: CustomRequestStatus, target: CustomRequestStatus
) -> None:
    with pytest.raises(InvalidCustomRequestTransitionError):
        plan_transition(current, target, _amount(target))


def test_the_matrix_covers_all_pairs() -> None:
    assert len(LEGAL) + len(ILLEGAL) == len(S) ** 2 == 49


@pytest.mark.parametrize("source", [S.NEW, S.IN_PROGRESS, S.COMPLETED, S.CLOSED, S.LOST])
def test_lost_is_reachable_only_from_contacted_or_quoted(source: CustomRequestStatus) -> None:
    with pytest.raises(InvalidCustomRequestTransitionError):
        plan_transition(source, S.LOST)


@pytest.mark.parametrize(
    ("current", "target", "stamp", "outcome"),
    [
        (S.NEW, S.CONTACTED, "contacted_at", None),
        (S.CONTACTED, S.QUOTED, "quoted_at", None),
        (S.CONTACTED, S.LOST, "closed_at", OUT.LOST),
        (S.QUOTED, S.LOST, "closed_at", OUT.LOST),
        (S.QUOTED, S.IN_PROGRESS, None, OUT.WON),
        (S.IN_PROGRESS, S.COMPLETED, "completed_at", None),
        (S.COMPLETED, S.CLOSED, "closed_at", None),
    ],
)
def test_each_edge_stamps_its_time_and_derives_the_outcome(
    current: CustomRequestStatus,
    target: CustomRequestStatus,
    stamp: str | None,
    outcome: CustomRequestOutcome | None,
) -> None:
    change = plan_transition(current, target, _amount(target))
    assert (change.stamp, change.outcome) == (stamp, outcome)
    assert change.quoted_amount_cents == _amount(target)


@pytest.mark.parametrize("amount", [None, QUOTE_MIN_CENTS - 1, QUOTE_MAX_CENTS + 1, -5])
def test_quoted_requires_an_amount_in_bounds(amount: int | None) -> None:
    with pytest.raises(InvalidQuoteError):
        plan_transition(S.CONTACTED, S.QUOTED, amount)


@pytest.mark.parametrize("amount", [QUOTE_MIN_CENTS, QUOTE_MAX_CENTS])
def test_quote_bounds_are_inclusive(amount: int) -> None:
    assert plan_transition(S.CONTACTED, S.QUOTED, amount).quoted_amount_cents == amount


@pytest.mark.parametrize("target", [t for t in S if t is not S.QUOTED])
def test_an_amount_is_refused_on_every_other_target(target: CustomRequestStatus) -> None:
    with pytest.raises(InvalidQuoteError):
        check_quote(target, 100)


def _attachment(expires_at: datetime) -> CustomRequestAttachment:
    return CustomRequestAttachment(
        id=uuid.uuid4(),
        custom_request_id=uuid.uuid4(),
        storage_key=f"custom-requests/{uuid.uuid4()}.png",
        original_filename="photo.png",
        mime_type="image/png",
        size_bytes=9,
        checksum="0" * 64,
        expires_at=expires_at,
        created_at=expires_at - timedelta(days=90),
    )


@pytest.mark.parametrize(("offset", "expired"), [(-1, False), (0, True), (1, True)])
def test_expiry_matches_the_purge_boundary(offset: int, expired: bool) -> None:
    expires_at = datetime(2026, 10, 17, 12, tzinfo=UTC)
    now = expires_at + timedelta(seconds=offset)
    assert is_expired(_attachment(expires_at), now) is expired


@pytest.mark.parametrize(
    ("original", "mime", "expected"),
    [
        ("photo.png", "image/png", "photo.png"),
        ("evil.html", "image/jpeg", "evil.jpg"),
        ("no-extension", "image/webp", "no-extension.webp"),
        ("archive.tar.gz", "image/png", "archive.tar.png"),
        ("../../etc/passwd", "image/png", "passwd.png"),
        ('quo"te\r\n.png', "image/jpeg", 'quo"te.jpg'),
        (".png", "image/png", ".png.png"),
        ("", "image/jpeg", "image.jpg"),
        ("صورة.jpeg", "image/jpeg", "صورة.jpg"),
    ],
)
def test_download_name_carries_the_stored_type(original: str, mime: str, expected: str) -> None:
    assert download_filename(original, mime) == expected


@pytest.mark.parametrize(
    "module",
    [
        "app.engagement.application.commands.custom_request_pipeline",
        "app.engagement.api.custom_request_admin",
        "app.engagement.infrastructure.custom_requests",
    ],
)
def test_the_pipeline_cannot_reach_orders_or_payments(module: str) -> None:
    """FR-15 negative: a lead never transacts (BR-112), so no path into those contexts."""
    source = Path(importlib.import_module(module).__file__ or "").read_text(encoding="utf-8")
    imported = {
        name
        for node in ast.walk(ast.parse(source))
        for name in (
            [node.module or ""]
            if isinstance(node, ast.ImportFrom)
            else [a.name for a in node.names]
            if isinstance(node, ast.Import)
            else []
        )
    }
    assert not {m for m in imported if m.startswith(("app.ordering", "app.payments"))}
