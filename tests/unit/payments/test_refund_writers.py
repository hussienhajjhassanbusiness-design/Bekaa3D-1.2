"""U12 and LO1 (VS-030 plan 6.1, 6.4): every writer of `refunds` and `refund_items`,
listed, and the use cases take orders, then payments, then the refund, in that order.
A new writer, or a reordered lock, fails here and forces the ADR-024 d9 re-check."""

import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "app"
SERVICES = SRC / "payments" / "application" / "services" / "refunds.py"
RAW_SQL = re.compile(
    r"\b(?:UPDATE|DELETE\s+FROM|INSERT\s+INTO)\s+(?:refunds|refund_items|chargebacks)\b",
    re.IGNORECASE,
)
MODELS = {"RefundModel", "RefundItemModel", "ChargebackModel", "ChargebackItemModel"}

KNOWN_WRITERS = {
    ("payments/infrastructure/refunds.py", "insert"),
    ("payments/infrastructure/refunds.py", "insert_late_capture"),
    ("payments/infrastructure/chargebacks.py", "_insert"),  # rank 5, after the refunds
    ("payments/infrastructure/refunds.py", "_move"),
    ("payments/infrastructure/refunds.py", "void"),
    ("payments/infrastructure/refunds.py", "mark_reissued"),
}
# Store writes -> the use cases allowed to call them, each after `_lock` (orders first).
STORE_WRITES = {"insert", "insert_late_capture", "settle", "fail", "void", "mark_reissued"}
STORES = {"refunds", "chargebacks"}
KNOWN_STORE_CALLERS = {
    "create_refund",
    "create_late_capture_refund",  # VS-024's Tx B holds ranks 1-3 (test below)
    "record_chargeback",
    "_void_and_remainders",  # called by record_chargeback after rank 4 (test below)
    "settle_refund",
    "fail_refund",
    "void_refund",
    "reissue_refund",
}


def _aliases(tree: ast.Module) -> set[str]:
    names = set(MODELS)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target, value in _pairs(node):
                if (
                    isinstance(target, ast.Name)
                    and isinstance(value, ast.Name)
                    and value.id in names
                ):
                    names.add(target.id)
    return names


def _pairs(node: ast.Assign) -> list[tuple[ast.expr, ast.expr]]:
    pairs: list[tuple[ast.expr, ast.expr]] = []
    for target in node.targets:
        if isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple):
            pairs += list(zip(target.elts, node.value.elts, strict=False))
        else:
            pairs.append((target, node.value))
    return pairs


def _functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]


def _writers() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in SRC.rglob("*.py"):
        module = path.relative_to(SRC).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = _aliases(tree)
        for function in _functions(tree):
            for node in ast.walk(function):
                orm = (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in {"insert", "pg_insert", "update", "delete"}
                    and node.args
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id in aliases
                )
                raw = (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and RAW_SQL.search(node.value) is not None
                )
                if orm or raw:
                    found.add((module, function.name))
    return found


def test_every_refund_writer_is_known() -> None:
    assert _writers() == KNOWN_WRITERS, (
        "A new writer of refunds or refund_items: it must run under the order's lock "
        "(VS-030 plan 8.1), through a use case listed below."
    )


def _store_calls(function: ast.AST) -> set[str]:
    return {
        node.func.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and (
            (isinstance(node.func.value, ast.Attribute) and node.func.value.attr in STORES)
            or (isinstance(node.func.value, ast.Name) and node.func.value.id in STORES)
        )
        and node.func.attr in STORE_WRITES
    }


def test_only_the_use_cases_call_the_store_writes() -> None:
    callers: set[str] = set()
    for path in SRC.rglob("*.py"):
        for function in _functions(ast.parse(path.read_text(encoding="utf-8"))):
            if _store_calls(function):
                callers.add(function.name)
    assert callers == KNOWN_STORE_CALLERS


def _first_line(function: ast.AST, attr: str) -> int:
    lines = [
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Attribute) and node.func.attr == attr)
            or (isinstance(node.func, ast.Name) and node.func.id == attr)
        )
    ]
    assert lines, f"{getattr(function, 'name', '?')} never calls {attr}"
    return min(lines)


def _service(name: str) -> ast.AsyncFunctionDef:
    tree = ast.parse(SERVICES.read_text(encoding="utf-8"))
    found = next(f for f in _functions(tree) if f.name == name)
    assert isinstance(found, ast.AsyncFunctionDef)
    return found


def test_lo1_the_lock_step_takes_orders_then_payments_then_reads_refunds() -> None:
    lock = _service("_lock")
    assert (
        _first_line(lock, "lock")
        < _first_line(lock, "lock_for_order")
        < _first_line(lock, "for_order")
        < _first_line(lock, "check_order_totals")
    )


def test_lo1_every_use_case_locks_before_it_writes() -> None:
    locked_refund = _service("_locked_refund")
    assert _first_line(locked_refund, "_lock") < _first_line(locked_refund, "lock")
    create = _service("create_refund")
    assert _first_line(create, "_lock") < _first_line(create, "insert")
    for name in ("settle_refund", "fail_refund", "void_refund", "reissue_refund"):
        function = _service(name)
        first_write = min(_first_line(function, w) for w in _store_calls(function))
        assert _first_line(function, "_locked_refund") < first_write, name


def test_lo1_a_late_capture_refund_locks_like_the_others() -> None:
    late = _service("_lock_late")
    assert _first_line(late, "lock") < _first_line(late, "lock_for_order")
    locked_refund = _service("_locked_refund")
    assert _first_line(locked_refund, "_lock_late") < _first_line(locked_refund, "lock")


def test_lo1_the_late_capture_sink_runs_after_the_order_and_payment_locks() -> None:
    """Plan 8.1 path 5: the obligation is inserted at rank 4, inside apply_result's Tx B."""
    apply = SRC / "payments" / "application" / "services" / "apply.py"
    tree = ast.parse(apply.read_text(encoding="utf-8"))
    result = next(f for f in _functions(tree) if f.name == "apply_result")
    late = next(f for f in _functions(tree) if f.name == "_late_capture")
    assert (
        _first_line(result, "lock")
        < _first_line(result, "decide")
        < _first_line(result, "_late_capture")
    )
    assert _first_line(late, "mark_late_capture") < _first_line(late, "late_capture_recorded")


def test_lo1_a_chargeback_locks_orders_payments_open_refunds_then_inserts() -> None:
    """Plan 8.1 path 6: ranks 1-2, 3, the refund reads, 4, then 5 (the chargeback INSERT)."""
    path = SRC / "payments" / "application" / "services" / "chargebacks.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    record = next(f for f in _functions(tree) if f.name == "record_chargeback")
    assert (
        _first_line(record, "lock")
        < _first_line(record, "lock_for_order")
        < _first_line(record, "for_order")
        < _first_line(record, "lock_open_for_payment")
        < _first_line(record, "_void_and_remainders")
        < _first_line(record, "insert")
    )
