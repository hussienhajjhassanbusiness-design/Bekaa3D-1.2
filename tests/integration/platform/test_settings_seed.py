"""The seeded registry, checked against real PostgreSQL.

The seed is what makes "settings exist immediately after deployment" true, and
it is written literally into migration `de1d8a23512f` rather than generated from
the registry - so nothing but a test holds the two in agreement. That is what
this file is.
"""

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.domain.settings_registry import REGISTRY
from app.platform.infrastructure.models import SettingModel

# The five that are legitimately unconfigured at deploy time: the optional
# free-shipping threshold, and three values still awaited from the client.
UNCONFIGURED = ("free_shipping_threshold", "pickup_address", "pickup_hours", "whatsapp_number")


@pytest.mark.integration
async def test_every_registered_setting_is_seeded_and_nothing_else_is(
    db_session: AsyncSession,
) -> None:
    """Both directions. A missing row means a consumer fails at runtime; an
    extra row means a key exists that no code knows how to validate."""
    rows = (await db_session.scalars(select(SettingModel))).all()
    assert {row.key for row in rows} == set(REGISTRY)
    assert len(rows) == 12


@pytest.mark.integration
async def test_the_stored_type_matches_the_registry_for_every_key(
    db_session: AsyncSession,
) -> None:
    """The declared type lives in two places - the `type` column written by the
    migration, and the registry that validates against it. They are meant to be
    one fact, and this is the only thing that keeps them one fact."""
    rows = (await db_session.scalars(select(SettingModel))).all()
    for row in rows:
        assert row.type is REGISTRY[row.key].type, row.key


@pytest.mark.integration
async def test_the_seeded_values_are_the_registry_defaults(db_session: AsyncSession) -> None:
    rows = (await db_session.scalars(select(SettingModel))).all()
    for row in rows:
        assert row.value == REGISTRY[row.key].default, row.key


@pytest.mark.integration
async def test_unconfigured_settings_store_json_null_not_sql_null(
    db_session: AsyncSession,
) -> None:
    """The distinction the whole optional-setting design rests on.

    `value` is `JSONB NOT NULL`, so SQL NULL is forbidden - but JSON has its own
    null, and that is what an unconfigured setting holds: a present document
    whose content is `null`. Asked through SQLAlchemy both look like Python
    `None`, so this asks PostgreSQL directly: `value IS NULL` must be false
    while `jsonb_typeof(value)` says 'null'.
    """
    result = await db_session.execute(
        text(
            "SELECT key, value IS NULL AS sql_null, jsonb_typeof(value) AS json_type "
            "FROM settings WHERE key = ANY(:keys)"
        ),
        {"keys": list(UNCONFIGURED)},
    )
    rows = {row.key: (row.sql_null, row.json_type) for row in result}

    assert set(rows) == set(UNCONFIGURED)
    for key, (sql_null, json_type) in rows.items():
        assert sql_null is False, f"{key} was stored as SQL NULL"
        assert json_type == "null", f"{key} should hold JSON null, got {json_type}"


@pytest.mark.integration
async def test_the_key_is_unique_at_the_database(db_session: AsyncSession) -> None:
    """Enforced by a constraint rather than by application checks, because an
    application check loses the race (CLAUDE.md invariants)."""
    db_session.add(
        SettingModel(key="accepting_orders", type=REGISTRY["accepting_orders"].type, value=True)
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_deleting_the_editing_administrator_keeps_the_setting(
    db_session: AsyncSession,
) -> None:
    """`updated_by` is ON DELETE SET NULL, matching audit_logs.actor_user_id:
    the record of what a setting is must outlive the account that changed it.

    A hard user delete only happens through the unverified-account purge, so
    this is defensive - but a cascade here would silently destroy configuration.
    """
    from app.identity.infrastructure.models import UserModel

    admin = UserModel(email=f"test-{uuid.uuid4().hex}@example.com", password_hash="x")
    db_session.add(admin)
    await db_session.flush()

    setting = await db_session.scalar(
        select(SettingModel).where(SettingModel.key == "daily_download_cap")
    )
    assert setting is not None
    setting.updated_by = admin.id
    await db_session.flush()

    await db_session.delete(admin)
    await db_session.flush()
    await db_session.refresh(setting)

    assert setting.updated_by is None
    assert setting.value == 20
    await db_session.rollback()
