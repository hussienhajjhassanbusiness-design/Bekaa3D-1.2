"""No code path updates an order's snapshots (VS-028 plan D13, Q9). The address, phone, hash,
lead time and dispatch columns are written by the INSERT only; no trigger guards them."""

import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "app"
MUTABLE = {
    "status",
    "updated_at",
    "cancelled_at",
    "completed_at",
    "admin_note",
    "customer_cancelled_at",  # VS-031: an event, not a snapshot
}
# VS-045 (ADR-047): the one module that rewrites snapshots, and only by stripping them.
ERASURE_MODULE = "ordering/infrastructure/erasure.py"
ERASED = {
    "customer_email_snapshot",
    "recipient_name",
    "contact_phone_snapshot",
    "contact_phone_hash",
    "city",
    "area",
    "street",
    "landmark_notes",
    "customer_note",
    "anonymized_at",
    "updated_at",
}
RAW_UPDATE = re.compile(
    r"\bUPDATE\s+orders\s+SET\s+(.*?)(?:\bWHERE\b|$)", re.IGNORECASE | re.DOTALL
)


def _order_aliases(tree: ast.Module) -> set[str]:
    names = {"OrderModel"}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Tuple)
            and isinstance(node.targets[0], ast.Tuple)
        ):
            for target, value in zip(node.targets[0].elts, node.value.elts, strict=False):
                if (
                    isinstance(target, ast.Name)
                    and isinstance(value, ast.Name)
                    and value.id in names
                ):
                    names.add(target.id)
        elif (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Name)
            and node.value.id in names
        ):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return names


def _updated_columns() -> dict[str, set[str]]:
    """module -> every keyword passed to `.values(...)` in a function that updates orders."""
    found: dict[str, set[str]] = {}
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = _order_aliases(tree)
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            nodes = list(ast.walk(function))
            updates = any(
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "update"
                and n.args
                and isinstance(n.args[0], ast.Name)
                and n.args[0].id in aliases
                for n in nodes
            )
            if not updates:
                continue
            columns = found.setdefault(path.relative_to(SRC).as_posix(), set())
            for n in nodes:
                is_values = (
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "values"
                )
                if is_values and isinstance(n, ast.Call):
                    columns |= {k.arg for k in n.keywords if k.arg}
    return found


def test_orm_updates_of_orders_write_only_the_mutable_columns() -> None:
    found = _updated_columns()
    assert found, "the scan found no writer of orders: it is broken"
    assert found.get(ERASURE_MODULE) == ERASED, "the erasure writes exactly the erased set"
    for module, columns in found.items():
        allowed = ERASED if module == ERASURE_MODULE else MUTABLE
        assert columns <= allowed, f"{module} updates snapshot columns: {columns - allowed}"


def test_raw_updates_of_orders_write_only_the_mutable_columns() -> None:
    for path in SRC.rglob("*.py"):
        for match in RAW_UPDATE.finditer(path.read_text(encoding="utf-8")):
            columns = set(re.findall(r"(\w+)\s*=", match.group(1)))
            assert columns <= MUTABLE, f"{path.name}: {columns - MUTABLE}"
