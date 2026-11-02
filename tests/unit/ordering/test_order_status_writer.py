"""VS-029 "Done when": no route sets `orders.status` directly (audit A-06). The status is a
projection, so its only writer is `recompute_order_status`, through one store method."""

import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "app"
RAW_STATUS_UPDATE = re.compile(r"\bUPDATE\s+orders\s+SET\b[^;]*\bstatus\b", re.IGNORECASE)
STORE_WRITER = ("ordering/infrastructure/orders.py", "set_order_status")


def _functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]


def _order_aliases(tree: ast.Module) -> set[str]:
    names = {"OrderModel"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Tuple | ast.Name):
            targets = node.targets[0]
            pairs = (
                zip(targets.elts, node.value.elts, strict=False)
                if isinstance(targets, ast.Tuple) and isinstance(node.value, ast.Tuple)
                else [(targets, node.value)]
            )
            for target, value in pairs:
                if (
                    isinstance(target, ast.Name)
                    and isinstance(value, ast.Name)
                    and value.id in names
                ):
                    names.add(target.id)
    return names


def _sets_status(function: ast.AST) -> bool:
    for node in ast.walk(function):
        if isinstance(node, ast.keyword) and node.arg == "status":
            return True
        if isinstance(node, ast.Dict) and any(
            isinstance(k, ast.Constant) and k.value == "status" for k in node.keys
        ):
            return True
    return False


def _status_writers() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in SRC.rglob("*.py"):
        module = path.relative_to(SRC).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = _order_aliases(tree)
        for function in _functions(tree):
            updates_orders = any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "update"
                and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in aliases
                for node in ast.walk(function)
            )
            raw = any(
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and RAW_STATUS_UPDATE.search(node.value) is not None
                for node in ast.walk(function)
            )
            if raw or (updates_orders and _sets_status(function)):
                found.add((module, function.name))
    return found


def _callers(name: str) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in _functions(tree):
            for node in ast.walk(function):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == name
                ):
                    found.add((path.relative_to(SRC).as_posix(), function.name))
    return found


def test_only_the_store_method_updates_the_order_status() -> None:
    assert _status_writers() == {STORE_WRITER}


def test_only_the_recompute_calls_the_store_method() -> None:
    assert _callers("set_order_status") == {("ordering/public.py", "recompute_order_status")}


def test_the_scan_sees_a_direct_status_update() -> None:
    """Guards the scan itself: a route-style direct write must be found."""
    probe = ast.parse(
        "_O = OrderModel\n"
        "async def route(s):\n    await s.execute(update(_O).values(status='completed'))\n"
    )
    [route] = [f for f in _functions(probe) if f.name == "route"]
    assert "_O" in _order_aliases(probe) and _sets_status(route)
