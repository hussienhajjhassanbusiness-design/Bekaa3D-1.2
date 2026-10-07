"""Other contexts may not reach into Engagement's table.

`create_notification` is the sanctioned write port. The rule that everyone else
goes through it is only worth stating if something checks it, so this reads the
source tree rather than trusting review to catch a direct import.

Deliberately a source scan and not an import-graph walk: the failure being
guarded against is someone *writing* `NotificationRepository(session).add(...)`
in the payments context, and that is visible in the text.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "app"

# Names that belong to Engagement's infrastructure and must not appear outside it.
FORBIDDEN = ("NotificationModel", "NotificationRepository", "engagement.infrastructure")

# The one legitimate exception, and the reason it is legitimate: importing every
# context's models is exactly what this module is for. Without it SQLAlchemy's
# cross-context foreign-key resolution fails, because it does not know about a
# table whose model class was never imported in that process. It imports the
# module and touches nothing in it.
ALLOWED = {SRC / "core" / "models.py"}


def _sources() -> list[Path]:
    return [
        path
        for path in SRC.rglob("*.py")
        if "engagement" not in path.relative_to(SRC).parts and path not in ALLOWED
    ]


def test_the_boundary_test_is_actually_looking_at_something() -> None:
    """A scan that silently matched no files would pass for ever. Guards the
    path arithmetic above, which is the part most likely to rot."""
    sources = _sources()
    assert len(sources) > 20, f"expected to scan the whole tree, found {len(sources)} files"
    assert SRC / "core" / "models.py" not in sources


def test_no_context_outside_engagement_touches_the_notifications_table() -> None:
    offenders: list[str] = []
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        for name in FORBIDDEN:
            if name in text:
                offenders.append(f"{path.relative_to(SRC)} references {name}")
    assert not offenders, (
        "these modules reach into Engagement's infrastructure directly; "
        "call create_notification instead: " + "; ".join(offenders)
    )


def test_no_module_writes_raw_sql_against_the_notifications_table() -> None:
    """The other half of the same rule. A context could avoid the model names
    and still write `INSERT INTO notifications`, which is the same violation
    with extra steps."""
    pattern = re.compile(r"(insert\s+into|update|from|join)\s+notifications\b", re.IGNORECASE)
    offenders = [
        str(path.relative_to(SRC)) for path in _sources() if pattern.search(path.read_text("utf-8"))
    ]
    assert not offenders, f"raw SQL against notifications outside Engagement: {offenders}"
