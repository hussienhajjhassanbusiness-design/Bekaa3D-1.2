"""The cash lock order, read from the code (VS-028 plan 6.1, Revision 1 item 1): in
`place_order` the cart lock comes first, then the address share lock, then the phone lock."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "app"
PHONE_LOCK_CALLS = {"lock_phone", "lock_cash_phone", "_lock_cash_phone"}
# (module, function) pairs allowed to call the phone lock; VS-031's cancel shows below
# that its cart lock comes first.
ALLOWED_CALLERS = {
    ("ordering/application/services/checkout.py", "place_order"),
    ("fulfillment/infrastructure/delivery_side.py", "insert_cash_block"),  # VS-031
    ("ordering/infrastructure/cash.py", "lock_phone"),
    ("ordering/public.py", "lock_cash_phone"),
}


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return node.func.id if isinstance(node.func, ast.Name) else None


def _functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]


def test_place_order_locks_the_cart_then_the_address_then_the_phone() -> None:
    path = SRC / "ordering" / "application" / "services" / "checkout.py"
    place = next(
        f for f in _functions(ast.parse(path.read_text("utf-8"))) if f.name == "place_order"
    )
    calls = sorted(
        (n for n in ast.walk(place) if isinstance(n, ast.Call)),
        key=lambda n: (n.lineno, n.col_offset),
    )
    order = [_call_name(c) for c in calls]
    first = {
        name: order.index(name)
        for name in ("lock_cart_for_checkout", "lock_for_share", "lock_phone")
    }
    assert first["lock_cart_for_checkout"] < first["lock_for_share"] < first["lock_phone"]
    assert order.index("insert_order") > first["lock_phone"]


def test_the_phone_lock_is_called_from_nowhere_else() -> None:
    callers: set[tuple[str, str]] = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in _functions(tree):
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and _call_name(node) in PHONE_LOCK_CALLS:
                    callers.add((path.relative_to(SRC).as_posix(), function.name))
    assert callers == ALLOWED_CALLERS


def test_the_cancel_locks_the_cart_then_the_phone_then_inserts_the_block() -> None:
    """VS-031 (ADR-024 d9): after the orders lock, which `insert_cash_block` runs under."""
    path = SRC / "fulfillment" / "infrastructure" / "delivery_side.py"
    block = next(
        f for f in _functions(ast.parse(path.read_text("utf-8"))) if f.name == "insert_cash_block"
    )
    calls = sorted(
        (n for n in ast.walk(block) if isinstance(n, ast.Call)),
        key=lambda n: (n.lineno, n.col_offset),
    )
    order = [_call_name(c) for c in calls]
    cart, phone = order.index("lock_cart_for_cash_block"), order.index("lock_cash_phone")
    assert cart < phone < order.index("insert_block")
