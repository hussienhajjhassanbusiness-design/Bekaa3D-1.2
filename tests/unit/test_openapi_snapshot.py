"""The OpenAPI file handed to the frontend team (docs/frontend-handoff) matches the code.
A stale file is worse than none: the frontend would build against routes that moved."""

import json
from pathlib import Path

from app.main import app

SNAPSHOT = Path(__file__).resolve().parents[2] / "docs" / "frontend-handoff" / "openapi.json"


def test_the_committed_openapi_document_matches_the_application() -> None:
    committed = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    current = json.loads(json.dumps(app.openapi()))
    assert committed == current, "Run `python scripts/export_openapi.py` and commit the result."
