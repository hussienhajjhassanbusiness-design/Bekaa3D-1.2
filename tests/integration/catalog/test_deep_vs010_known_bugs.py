"""VS-010 issues found by the slice audit, locked in as strict xfails.

VS-010 is outside the deep-test range (VS-001..009); these exist only so the
audit's known catalogue bugs flip to passing when fixed.
"""

import base64
import json
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app as main_app
from tests.integration.deep_support import assert_problem, client_for, csrf, mfa_admin


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("path", "body"),
    [
        (
            "/api/v1/admin/categories",
            {"name": "Lamp\u0000s", "slug": f"nul-{uuid.uuid4().hex[:8]}"},
        ),
        ("/api/v1/admin/materials", {"name": "Res\u0000in"}),
        ("/api/v1/admin/colours", {"name": "Re\u0000d"}),
    ],
    ids=["category", "material", "colour"],
)
async def test_a_nul_in_a_reference_name_is_a_422(
    path: str, body: dict[str, str], db_session: AsyncSession
) -> None:
    with client_for(main_app, raise_server_exceptions=False) as client:
        await mfa_admin(client, db_session)
        response = client.post(path, json=body, headers=csrf(client))
    assert_problem(response, 422, "VALIDATION_ERROR")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_nul_in_a_decoded_cursor_is_a_422(db_session: AsyncSession) -> None:
    cursor = (
        base64.urlsafe_b64encode(json.dumps({"n": "\u0000", "i": str(uuid.uuid4())}).encode())
        .decode()
        .rstrip("=")
    )
    with client_for(main_app, raise_server_exceptions=False) as client:
        await mfa_admin(client, db_session)
        response = client.get("/api/v1/admin/categories", params={"cursor": cursor})
    assert_problem(response, 422, "VALIDATION_ERROR")
