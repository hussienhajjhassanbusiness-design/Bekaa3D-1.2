"""Every writer of `order_items`, listed (VS-023 Checkpoint 4). The lines lock in
`SqlOrderStore.lock_lines` is redundant only while each writer of an existing line holds
the order's lock first; a new writer fails here and forces that re-check (ADR-024 d9)."""

import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "app"
RAW_SQL = re.compile(r"\b(?:UPDATE|DELETE\s+FROM|INSERT\s+INTO)\s+order_items\b", re.IGNORECASE)

# (module, function) -> why the lines lock is not needed for it.
KNOWN_WRITERS = {
    ("ordering/infrastructure/orders.py", "insert_lines"): "new rows, invisible until commit",
    ("ordering/infrastructure/orders.py", "set_line_status"): "only under the orders lock",
    ("ordering/infrastructure/orders.py", "set_line_delivered"): "only under the orders lock",
}
# Callers of `set_line_status`: each must hold `lock_order_for_change`'s locks.
KNOWN_LINE_STATUS_CALLERS = {
    ("ordering/public.py", "mark_order_paid"),
    ("ordering/public.py", "release_unpaid_order"),  # VS-024 plan 6.1
}


def _aliases(tree: ast.Module) -> set[str]:
    """Names bound to OrderItemModel: the class itself and `_I = OrderItemModel` style."""
    names = {"OrderItemModel"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            pairs: list[tuple[ast.expr, ast.expr]] = []
            for target in node.targets:
                if isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple):
                    pairs += list(zip(target.elts, node.value.elts, strict=False))
                else:
                    pairs.append((target, node.value))
            for target, value in pairs:
                if (
                    isinstance(target, ast.Name)
                    and isinstance(value, ast.Name)
                    and value.id in names
                ):
                    names.add(target.id)
    return names


def _functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]


def _writers() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in SRC.rglob("*.py"):
        module = path.relative_to(SRC).as_posix()
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        aliases = _aliases(tree)
        for function in _functions(tree):
            for node in ast.walk(function):
                orm_write = (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in {"insert", "update", "delete"}
                    and node.args
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id in aliases
                )
                raw_write = (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and RAW_SQL.search(node.value) is not None
                )
                if orm_write or raw_write:
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


def test_every_order_items_writer_is_known() -> None:
    assert _writers() == set(KNOWN_WRITERS), (
        "A new writer of order_items: check it takes the orders lock first (ADR-024 d9), "
        "then list it here."
    )


def test_line_statuses_change_only_under_the_orders_lock() -> None:
    assert _callers("set_line_status") == KNOWN_LINE_STATUS_CALLERS
    source = (SRC / "ordering" / "public.py").read_text(encoding="utf-8")
    mark = next(f for f in _functions(ast.parse(source)) if f.name == "mark_order_paid")
    assert any(arg.arg == "locked" for arg in mark.args.args), "takes a LockedOrder"


def test_a_delivery_is_written_only_under_the_orders_lock() -> None:
    assert _callers("set_line_delivered") == {("ordering/public.py", "mark_stl_line_delivered")}
    source = (SRC / "ordering" / "public.py").read_text(encoding="utf-8")
    mark = next(f for f in _functions(ast.parse(source)) if f.name == "mark_stl_line_delivered")
    assert any(arg.arg == "locked" for arg in mark.args.args), "takes a LockedOrder"


def test_only_the_delivery_writer_sets_fulfilled_at_or_delivered_by() -> None:
    pattern = re.compile(r"\.values\([^)]*(fulfilled_at|delivered_by)")
    hits = {
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if pattern.search(path.read_text("utf-8"))
    }
    assert hits == {"ordering/infrastructure/orders.py"}
