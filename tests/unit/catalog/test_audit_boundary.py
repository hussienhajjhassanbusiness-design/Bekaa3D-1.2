"""Catalog must not reach into Platform's infrastructure.

Platform owns `audit_logs`. Cross-context access goes through a service
interface (CLAUDE.md, architecture rules), which for writing audit records is
`app.platform.application.services.audit_writer.AuditWriter`.

VS-010 originally imported `AuditLogRepository` directly from Platform's
infrastructure. That worked, but it is precisely the shared-database coupling
the modular monolith exists to prevent, so this test pins the boundary shut for
the Catalog context.

Deliberately scoped to `src/app/catalog` only. This slice is not refactoring the
project's historical audit call sites - Platform writing to its own table is not
a cross-context dependency - so a repo-wide rule here would be a wall of false
positives.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "app"
CATALOG = SRC / "catalog"

# Platform's internals. `app.platform.application` and `app.platform.domain` are
# the sanctioned surfaces and are deliberately absent from this list.
FORBIDDEN = ("app.platform.infrastructure", "AuditLogRepository")


def _catalog_sources() -> list[Path]:
    return sorted(CATALOG.rglob("*.py"))


def test_the_boundary_test_is_actually_looking_at_something() -> None:
    """A scan that silently matched no files would pass for ever. Guards the
    path arithmetic above, which is the part most likely to rot."""
    sources = _catalog_sources()
    assert len(sources) >= 8, f"expected the whole catalog package, found {len(sources)}"
    assert any(path.name == "category_admin.py" for path in sources)


def test_catalog_does_not_import_platform_infrastructure() -> None:
    offenders: list[str] = []
    for path in _catalog_sources():
        text = path.read_text(encoding="utf-8")
        for name in FORBIDDEN:
            if name in text:
                offenders.append(f"{path.relative_to(SRC)} references {name}")
    assert not offenders, (
        "Catalog must write audit records through "
        "app.platform.application.services.audit_writer.AuditWriter, not by "
        "importing Platform's infrastructure: " + "; ".join(offenders)
    )


def test_the_sanctioned_audit_port_is_what_catalog_uses() -> None:
    """Stated positively as well, so deleting the audit calls entirely would not
    quietly satisfy the rule above."""
    users = [
        path.name
        for path in _catalog_sources()
        if "audit_writer import AuditWriter" in path.read_text(encoding="utf-8")
    ]
    assert "category_admin.py" in users
    assert "value_admin.py" in users
