"""VS-013 smoke suite (admin products). Every point is already proven by the slice's
own tests, so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_CATALOG = "tests/integration/catalog"
_PRODUCTS = f"{_CATALOG}/test_admin_products.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "an admin creates and reads both product types": [
        f"{_PRODUCTS}::test_both_types_round_trip_with_version_and_zero_aggregates",
    ],
    "an STL product with physical fields cannot be stored, even via SQL": [
        f"{_CATALOG}/test_product_schema.py::test_an_stl_row_cannot_carry_any_physical_only_field",
        f"{_PRODUCTS}::test_an_stl_create_refuses_each_physical_field",
    ],
    "a stale edit gets 409 VERSION_CONFLICT and writes nothing": [
        f"{_PRODUCTS}::test_a_stale_version_is_409_with_the_current_version_and_writes_nothing",
    ],
    "a used category, material or colour cannot be archived": [
        f"{_CATALOG}/test_reference_in_use.py::test_a_value_a_live_product_uses_cannot_be_archived",
    ],
    "every product write is audited": [
        f"{_PRODUCTS}::test_every_successful_write_is_audited_with_actor_and_snapshots",
    ],
    "non-administrators cannot reach the product routes": [
        f"{_PRODUCTS}::test_anonymous_callers_get_401_and_customers_404_on_every_operation",
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs013_smoke_test_still_exists() -> None:
    missing = []
    for node_id in (n for ids in SMOKE_ELSEWHERE.values() for n in ids):
        path, _, name = node_id.partition("::")
        source = (_ROOT / path).read_text(encoding="utf-8") if (_ROOT / path).exists() else ""
        defined = {
            node.name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        if name not in defined:
            missing.append(node_id)
    assert not missing, f"listed smoke tests no longer exist: {missing}"
