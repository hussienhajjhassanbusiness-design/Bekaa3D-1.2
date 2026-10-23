"""VS-029 "done when": no route but the cash handover creates a cash payment (SRS 9.8.3,
BR-054, glossary rule 6). Every `payments` INSERT in `src/app` and its call chain is listed,
so a new writer or caller fails here."""

import ast
import re
from collections.abc import Callable
from functools import partial
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "app"
RAW_INSERT = re.compile(r"\bINSERT\s+INTO\s+payments\b", re.IGNORECASE)
PAYMENT_ALIASES = {"PaymentModel", "_P"}

KNOWN_INSERTS = {
    ("payments/infrastructure/cash_payments.py", "insert_cash_payment"),
    ("payments/infrastructure/payments.py", "insert_pending"),
}
# Each link of the only path to `insert_cash_payment`, and who may call it.
CASH_CHAIN = {
    "insert_cash_payment": {("fulfillment/infrastructure/delivery_side.py", "record_cash")},
    "record_cash": {("fulfillment/application/record_cash_handover.py", "record_cash_handover")},
    "record_cash_handover": {("fulfillment/api/admin_orders.py", "cash_handover")},
}


def _trees() -> list[tuple[str, ast.Module]]:
    return [
        (path.relative_to(SRC).as_posix(), ast.parse(path.read_text(encoding="utf-8")))
        for path in SRC.rglob("*.py")
    ]


def _functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]


def _is_payment_insert(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return RAW_INSERT.search(node.value) is not None
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "insert"
        and bool(node.args)
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id in PAYMENT_ALIASES
    )


def _called(node: ast.AST, name: str) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id == name) or (
        isinstance(func, ast.Attribute) and func.attr == name
    )


def _sites(predicate: Callable[[ast.AST], bool]) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for module, tree in _trees():
        for function in _functions(tree):
            if any(predicate(node) for node in ast.walk(function)):
                found.add((module, function.name))
    return found


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def test_every_payments_insert_is_known() -> None:
    assert _sites(_is_payment_insert) == KNOWN_INSERTS


def test_the_online_insert_can_only_write_an_online_payment() -> None:
    """`ck_payments_cash_iff_cash_order` then refuses `provider = 'cash'` on it."""
    [(module, tree)] = [t for t in _trees() if t[0] == "payments/infrastructure/payments.py"]
    [function] = [f for f in _functions(tree) if f.name == "insert_pending"]
    values = [n for n in ast.walk(function) if isinstance(n, ast.Call) and _called(n, "values")]
    methods = [_keyword(call, "order_payment_method") for call in values]
    assert [ast.literal_eval(m) for m in methods if m is not None] == ["online"], module


def test_only_the_handover_route_reaches_the_cash_insert() -> None:
    for name, callers in CASH_CHAIN.items():
        assert _sites(partial(_called, name=name)) == callers, name
