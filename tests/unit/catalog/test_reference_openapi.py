"""VS-010 audit A-11: every reference-data write that can answer 409 says so in OpenAPI, so a
generated client models `SLUG_CONFLICT` and `INVALID_STATE_TRANSITION`."""

import pytest

from app.main import app

ADMIN = "/api/v1/admin"
WRITES = [
    ("post", f"{ADMIN}/categories"),
    ("patch", f"{ADMIN}/categories/{{category_id}}"),
    ("delete", f"{ADMIN}/categories/{{category_id}}"),
    ("post", f"{ADMIN}/materials"),
    ("patch", f"{ADMIN}/materials/{{material_id}}"),
    ("delete", f"{ADMIN}/materials/{{material_id}}"),
    ("post", f"{ADMIN}/colours"),
    ("patch", f"{ADMIN}/colours/{{colour_id}}"),
    ("delete", f"{ADMIN}/colours/{{colour_id}}"),
]


@pytest.mark.parametrize(("method", "path"), WRITES)
def test_every_reference_write_documents_its_409(method: str, path: str) -> None:
    responses = app.openapi()["paths"][path][method]["responses"]
    assert "409" in responses, f"{method.upper()} {path}"
