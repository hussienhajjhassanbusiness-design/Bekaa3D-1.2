"""The ADR-005 architecture rules, checked statically over every module.

- domain        -> no framework, database or infrastructure imports
- application   -> depends on domain only (never infrastructure)
- cross-context -> through service interfaces only, never into another
                   context's infrastructure

Composition roots (`app.api`, `app.core`, `app.jobs`, `app.integrations`,
`app.main`, `app.worker`) wire contexts together and are exempt.
"""

import ast
from collections.abc import Callable
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
CONTEXTS = (
    "catalog",
    "engagement",
    "fulfillment",
    "identity",
    "negotiation",
    "ordering",
    "payments",
    "platform",
    "reporting",
)
FRAMEWORKS = ("fastapi", "starlette", "sqlalchemy", "asyncpg", "redis", "arq", "httpx")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _modules(context: str, layer: str | None = None) -> list[Path]:
    root = SRC / context / layer if layer else SRC / context
    return sorted(root.rglob("*.py")) if root.exists() else []


def _violations(
    context: str, layer: str | None, forbidden: Callable[[str], bool]
) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for path in _modules(context, layer):
        bad = sorted(name for name in _imports(path) if forbidden(name))
        if bad:
            out[str(path.relative_to(SRC))] = bad
    return out


def test_every_context_exists() -> None:
    assert all((SRC / c).is_dir() for c in CONTEXTS)


@pytest.mark.parametrize("context", CONTEXTS)
def test_the_domain_layer_is_pure(context: str) -> None:
    def forbidden(name: str) -> bool:
        return name.split(".")[0] in FRAMEWORKS or ".infrastructure" in name or ".api" in name

    assert _violations(context, "domain", forbidden) == {}


def test_no_context_imports_another_contexts_infrastructure() -> None:
    offences: dict[str, list[str]] = {}
    for context in CONTEXTS:

        def forbidden(name: str, own: str = context) -> bool:
            parts = name.split(".")
            return (
                len(parts) >= 3
                and parts[0] == "app"
                and parts[1] in CONTEXTS
                and parts[1] != own
                and parts[2] == "infrastructure"
            )

        offences.update(_violations(context, None, forbidden))
    assert offences == {}, offences


def _is_published_surface(name: str) -> bool:
    """`app.<context>.public` or `app.<context>.application.ports` (or under it)."""
    rest = name.split(".")[2:]
    return rest[:1] == ["public"] or rest[:2] == ["application", "ports"]


def test_cross_context_imports_go_only_through_public_or_ports() -> None:
    """VS-012c: a context reaches another only through what that context
    publishes - its `public` module or its `application.ports` - never its
    domain, application services, API layer or infrastructure directly."""
    offences: dict[str, list[str]] = {}
    published: set[str] = set()
    for context in CONTEXTS:

        def crosses(name: str, own: str = context) -> bool:
            parts = name.split(".")
            return (
                len(parts) >= 2 and parts[0] == "app" and parts[1] in CONTEXTS and parts[1] != own
            )

        for path, names in _violations(context, None, crosses).items():
            published.update(n for n in names if _is_published_surface(n))
            bad = [n for n in names if not _is_published_surface(n)]
            if bad:
                offences[path] = bad
    assert offences == {}, offences
    # Guards the scan itself: a rule that matched no cross-context import at
    # all would pass for ever.
    assert {"app.identity.public", "app.platform.public"} <= published, published


def test_the_application_layer_depends_on_the_domain_only() -> None:
    offences: dict[str, list[str]] = {}
    for context in CONTEXTS:
        offences.update(
            _violations(
                context,
                "application",
                lambda name: ".infrastructure" in name or name.split(".")[0] in FRAMEWORKS,
            )
        )
    assert offences == {}, offences


def test_notifications_are_written_only_through_the_port() -> None:
    """The one cross-context boundary the code already enforces - held."""
    offenders = {
        str(path.relative_to(SRC))
        for context in CONTEXTS
        if context != "engagement"
        for path in _modules(context)
        if any("app.engagement.infrastructure" in name for name in _imports(path))
    }
    assert offenders == set()
