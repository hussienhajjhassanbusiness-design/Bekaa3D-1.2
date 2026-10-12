"""Write the API's OpenAPI document to docs/frontend-handoff/openapi.json.
Run it after changing any route or schema: `python scripts/export_openapi.py`."""

import json
from pathlib import Path

from app.main import app

SNAPSHOT = Path(__file__).resolve().parents[1] / "docs" / "frontend-handoff" / "openapi.json"


def render() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    SNAPSHOT.write_text(render(), encoding="utf-8", newline="\n")
    print(f"Wrote {SNAPSHOT}")
