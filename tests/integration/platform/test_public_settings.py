"""`GET /api/v1/settings/public`: the five allowlisted keys, and nothing else.

This endpoint is unauthenticated and reads a table that also holds internal
business parameters - the offer floor, the abuse cap, the purge period. The
tests here are less about the happy path than about the property that an
internal setting cannot reach it, including one that has never been thought
about because it does not exist yet.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.domain.enums import SettingType
from app.platform.domain.settings_registry import PUBLIC_KEYS, REGISTRY
from app.platform.infrastructure.models import SettingModel

PUBLIC_PATH = "/api/v1/settings/public"

EXPECTED_FIELDS = {
    "accepting_orders",
    "free_shipping_threshold",
    "pickup_address",
    "pickup_hours",
    "whatsapp_number",
}


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_the_response_has_exactly_the_five_allowlisted_fields() -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.get(PUBLIC_PATH)

    assert response.status_code == 200
    assert set(response.json()) == EXPECTED_FIELDS
    assert set(PUBLIC_KEYS) == EXPECTED_FIELDS


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_no_internal_setting_appears_in_the_response() -> None:
    """Named explicitly rather than checked as "not in the allowlist", so the
    assertion still means something if the allowlist itself is widened by
    mistake."""
    from app.main import app

    with TestClient(app) as client:
        body = client.get(PUBLIC_PATH).json()

    for internal in (
        "offer_response_window",
        "offer_checkout_window",
        "offer_rejection_cooldown",
        "minimum_offer_percentage",
        "checkout_hold_period",
        "unverified_account_purge_period",
        "daily_download_cap",
    ):
        assert internal not in body, f"{internal} leaked to the public endpoint"
        assert REGISTRY[internal].is_public is False


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_setting_added_to_the_table_cannot_become_public_by_existing(
    db_session: AsyncSession,
) -> None:
    """The test that matters most, and the one a "select everything and filter"
    implementation would fail.

    A row is inserted straight into the table under a key the registry has never
    heard of - the shape a future slice's setting, or a bad migration, would
    take. The public response must be unchanged: the endpoint reads only the
    allowlisted keys, and the response model has no field for anything else, so
    two separate things would both have to break for this to escape.
    """
    from app.main import app

    rogue_key = f"internal_secret_{uuid.uuid4().hex[:8]}"
    db_session.add(
        SettingModel(
            key=rogue_key,
            type=SettingType.STRING,
            value="super-secret-provider-key",
            description="Should never be public.",
        )
    )
    await db_session.commit()

    try:
        with TestClient(app) as client:
            response = client.get(PUBLIC_PATH)

        assert response.status_code == 200
        assert set(response.json()) == EXPECTED_FIELDS
        assert "super-secret-provider-key" not in response.text
        assert rogue_key not in response.text
    finally:
        row = await db_session.scalar(select(SettingModel).where(SettingModel.key == rogue_key))
        if row is not None:
            await db_session.delete(row)
            await db_session.commit()


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_unconfigured_public_values_are_null_rather_than_invented() -> None:
    """The client has not supplied the address, hours or number yet (SRS 30.2).

    Null is the honest answer and lets the frontend hide the element; a
    placeholder would publish fiction to real customers.
    """
    from app.main import app

    with TestClient(app) as client:
        body = client.get(PUBLIC_PATH).json()

    assert body["pickup_address"] is None
    assert body["pickup_hours"] is None
    assert body["whatsapp_number"] is None
    assert body["free_shipping_threshold"] is None
    # The kill switch is not nullable - the shop is either open or closed.
    assert body["accepting_orders"] is False


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_endpoint_needs_no_authentication(db_session: AsyncSession) -> None:
    """It is on the public list in api-endpoints.md:230, alongside products and
    categories. No cookie is sent here at all."""
    from app.main import app

    with TestClient(app) as client:
        client.cookies.clear()
        response = client.get(PUBLIC_PATH)

    assert response.status_code == 200
