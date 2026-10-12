"""`scripts/dev_seed.py` (docs/frontend-handoff): the accounts and catalogue it promises,
idempotence, credential rotation, and its refusal outside development."""

import importlib.util
import json
from argparse import Namespace
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from types import ModuleType

import pyotp
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from tests.catalog_seed import register, retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import assert_problem, client_for

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dev_seed.py"
LOGIN = "/api/v1/auth/login"
VERIFY = "/api/v1/auth/mfa/verify"
PRODUCTS = "/api/v1/products"
VISIBLE = {
    "moon-lamp",
    "geometric-planter",
    "dragon",
    "cable-organizer",
    "name-sign",
    "knight",
    "dragon-stl",
    "phone-stand-stl",
    "low-poly-vase-stl",
}
_ACCEPTING = "SELECT value FROM settings WHERE key = 'accepting_orders'"
_SEEDED_IMAGES = (
    "SELECT count(*) FROM product_images i JOIN products p ON p.id = i.product_id "
    "WHERE p.deleted_at IS NULL AND p.description LIKE '%scripts/dev_seed.py%'"
)


@pytest_asyncio.fixture
async def dev_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configured_app: None, db_session: AsyncSession
) -> AsyncGenerator[ModuleType]:
    """The script as a module, writing images to a temporary directory."""
    monkeypatch.setenv("MEDIA_PUBLIC_DIR", str(tmp_path))
    get_settings.cache_clear()
    spec = importlib.util.spec_from_file_location("dev_seed", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    before = await db_session.scalar(text(_ACCEPTING))
    yield module
    # The suites share one database: put the kill switch back as it was found.
    await db_session.rollback()
    await db_session.execute(
        text("UPDATE settings SET value = CAST(:v AS jsonb) WHERE key = 'accepting_orders'"),
        {"v": json.dumps(before)},
    )
    await db_session.commit()


def _admin_login(client: TestClient, module: ModuleType, issued: dict[str, str]) -> None:
    challenge = client.post(
        LOGIN, json={"email": module.ADMIN_EMAIL, "password": issued["admin password"]}
    )
    assert challenge.status_code == 202, challenge.text
    code = pyotp.TOTP(issued["admin TOTP secret"]).now()
    verified = client.post(
        VERIFY, json={"challenge_id": challenge.json()["challenge_id"], "code": code}
    )
    assert verified.status_code == 204, verified.text


async def test_the_seed_gives_a_working_admin_customer_and_catalogue(
    dev_seed: ModuleType,
    db_session: AsyncSession,
    make_app: Callable[[], FastAPI],
) -> None:
    report = await dev_seed.seed(db_session)
    await db_session.commit()
    register(*report.reference_ids)
    assert (report.products_created, report.images_created) == (11, 12)
    assert await db_session.scalar(text(_SEEDED_IMAGES)) == 12

    app = make_app()
    with client_for(app) as admin:
        _admin_login(admin, dev_seed, report.issued)
        listed = admin.get("/api/v1/admin/products", params={"limit": 100})
        assert listed.status_code == 200, listed.text
    with client_for(app) as customer:
        password = report.issued["customer password"]
        session = customer.post(
            LOGIN, json={"email": dev_seed.CUSTOMER_EMAIL, "password": password}
        )
        assert session.status_code == 200, session.text
        assert session.json()["email_verified"] is True
        assert len(customer.get("/api/v1/me/notifications").json()["items"]) == 2
        assert_problem(customer.get("/api/v1/admin/products"), 404, "NOT_FOUND")

    with client_for(app) as visitor:
        details = {slug: visitor.get(f"{PRODUCTS}/{slug}") for slug in VISIBLE}
        assert {slug: r.status_code for slug, r in details.items()} == dict.fromkeys(VISIBLE, 200)
        assert all(r.json()["cover_image"] is not None for r in details.values())
        assert len(details["dragon"].json()["images"]) == 2
        assert details["knight"].json()["is_available"] is False
        sign = details["name-sign"].json()["capabilities"]
        assert (sign["can_add_to_cart"], sign["whatsapp_available"]) == (False, True)
        stl = details["dragon-stl"].json()
        assert (stl["type"], stl["purchase_mode"], stl["material"]) == ("stl", None, None)
        for hidden in ("prototype-gear", "holiday-ornament"):
            assert_problem(visitor.get(f"{PRODUCTS}/{hidden}"), 404, "NOT_FOUND")
        assert visitor.get("/api/v1/settings/public").json()["accepting_orders"] is True


async def test_a_second_run_adds_nothing_and_rotation_replaces_the_credentials(
    dev_seed: ModuleType, db_session: AsyncSession, make_app: Callable[[], FastAPI]
) -> None:
    first = await dev_seed.seed(db_session)
    await db_session.commit()
    register(*first.reference_ids)
    # Through the command-line entry point, which opens its own engine and commits.
    again = await dev_seed._run(Namespace(rotate_credentials=False, whatsapp_number=None))
    assert (again.products_created, again.images_created, again.issued) == (0, 0, {})
    assert again.reference_ids == []

    rotated = await dev_seed.seed(db_session, rotate=True)
    await db_session.commit()
    app = make_app()
    with client_for(app) as admin:
        _admin_login(admin, dev_seed, rotated.issued)
        assert admin.get("/api/v1/admin/settings").status_code == 200
    with client_for(app) as stale:
        old = {"email": dev_seed.CUSTOMER_EMAIL, "password": "not-the-seeded-password"}
        assert_problem(stale.post(LOGIN, json=old), 401, "INVALID_CREDENTIALS")


@pytest.mark.parametrize("environment", ["production", "staging", "prod"])
async def test_the_seed_refuses_to_run_outside_development(
    dev_seed: ModuleType,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", environment)
    get_settings.cache_clear()
    with pytest.raises(SystemExit, match="refuses to run"):
        await dev_seed.seed(db_session)
