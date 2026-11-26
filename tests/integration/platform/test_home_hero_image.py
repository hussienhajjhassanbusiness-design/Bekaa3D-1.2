"""The homepage hero image (docs/homepage-hero-image.md): the upload pipeline, the setting
it writes, the public read, the guards around both, and the reaping of replaced files."""

import os
import re
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.integrations.scanning.factory import get_malware_scanner
from app.integrations.scanning.fake import EICAR, FakeScanner
from app.integrations.storage.factory import get_public_media_storage
from app.integrations.storage.local import LocalStorage
from app.jobs.reap_orphan_files import GRACE_PERIOD, HERO_IMAGES, reap
from app.main import app as main_app
from app.platform.api.home_hero import MULTIPART_ALLOWANCE
from app.platform.application.commands.replace_hero_image import MAX_HERO_IMAGE_BYTES
from app.platform.infrastructure.models import AuditLogModel
from tests.image_samples import SECRET, sample
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

ADMIN_URL = "/api/v1/admin/home/hero-image"
PUBLIC_URL = "/api/v1/home/hero-image"
SETTING_URL = "/api/v1/admin/settings/homepage_hero_image"
URL_SHAPE = re.compile(r"^/media/home/hero/[0-9a-f]{32}\.(jpg|png|webp)$")
BIG_ENOUGH = (800, 600)


class Media:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.storage = LocalStorage(root)
        self.scanner = FakeScanner()

    def stored(self) -> list[str]:
        return sorted(
            p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file()
        )


@pytest.fixture
async def media(tmp_path: Path, db_engine: AsyncEngine) -> AsyncGenerator[Media]:
    """Overrides storage and scanner, and keeps the global setting at its default around
    each test."""

    async def _reset() -> None:
        async with db_engine.begin() as conn:
            await conn.execute(
                text("UPDATE settings SET value = 'null'::jsonb WHERE key = 'homepage_hero_image'")
            )

    await _reset()
    media = Media(tmp_path / "media")
    main_app.dependency_overrides[get_public_media_storage] = lambda: media.storage
    main_app.dependency_overrides[get_malware_scanner] = lambda: media.scanner
    yield media
    main_app.dependency_overrides.pop(get_public_media_storage, None)
    main_app.dependency_overrides.pop(get_malware_scanner, None)
    await _reset()


def _upload(
    client: TestClient,
    data: bytes,
    *,
    filename: str = "hero.png",
    content_type: str = "image/png",
    headers: dict[str, str] | None = None,
) -> Any:
    return client.put(
        ADMIN_URL,
        files={"file": (filename, data, content_type)},
        headers=csrf(client) if headers is None else headers,
    )


def _uploaded(client: TestClient, fmt: str = "PNG") -> str:
    response = _upload(client, sample(fmt, size=BIG_ENOUGH))
    assert response.status_code == 200, response.text
    url: str = response.json()["url"]
    assert URL_SHAPE.match(url), url
    return url


def _public(client: TestClient) -> str | None:
    response = client.get(PUBLIC_URL)
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"url"}
    url: str | None = response.json()["url"]
    return url


def _key(url: str) -> str:
    return url.removeprefix("/media/")


async def test_the_default_is_no_image(media: Media) -> None:
    with client_for(main_app) as anonymous:
        assert _public(anonymous) is None


@pytest.mark.parametrize(("fmt", "extension"), [("JPEG", "jpg"), ("PNG", "png"), ("WEBP", "webp")])
async def test_an_upload_is_reencoded_stored_and_served(
    db_session: AsyncSession, media: Media, fmt: str, extension: str
) -> None:
    upload = sample(fmt, size=BIG_ENOUGH)
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        admin_id = admin.id
        response = _upload(client, upload)
        assert response.status_code == 200, response.text
        url = response.json()["url"]
        setting = client.get(SETTING_URL).json()
    with client_for(main_app) as anonymous:
        assert _public(anonymous) == url

    assert url.endswith(f".{extension}")
    [stored] = media.stored()
    assert stored == _key(url) == setting["value"]
    data = (media.root / stored).read_bytes()
    assert data != upload and SECRET.encode() not in data
    assert media.scanner.scanned == [upload]
    db_session.expire_all()
    [audit] = (
        await db_session.scalars(
            select(AuditLogModel).where(
                AuditLogModel.action == "setting.updated",
                AuditLogModel.actor_user_id == admin_id,
            )
        )
    ).all()
    assert audit.before_data == {"key": "homepage_hero_image", "value": None}
    assert audit.after_data == {"key": "homepage_hero_image", "value": stored}


async def test_a_replacement_takes_over_and_the_old_file_is_reaped_later(
    db_session: AsyncSession, db_engine: AsyncEngine, media: Media
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        first = _uploaded(client)
        second = _uploaded(client, "JPEG")
    with client_for(main_app) as anonymous:
        assert _public(anonymous) == second

    # Not deleted on replace: a page that loaded the old URL a moment ago may still ask.
    assert sorted(media.stored()) == sorted([_key(first), _key(second)])
    old = datetime.now(UTC) - GRACE_PERIOD - timedelta(minutes=1)
    for key in media.stored():
        os.utime(media.root / key, (old.timestamp(), old.timestamp()))
    removed = await reap(
        media.storage, async_sessionmaker(db_engine), datetime.now(UTC), HERO_IMAGES
    )
    assert removed == [_key(first)]
    assert media.stored() == [_key(second)]


@pytest.mark.parametrize(
    ("data", "filename", "content_type"),
    [
        (b"just text", "hero.png", "image/png"),
        (b"GIF89a" + b"\x00" * 40, "hero.gif", "image/gif"),
        (b'<svg xmlns="http://www.w3.org/2000/svg"/>', "hero.png", "image/png"),
        (b"MZ" + b"\x00" * 100, "hero.exe", "application/octet-stream"),
        (b"", "hero.png", "image/png"),
    ],
    ids=["text-as-png", "gif", "svg-as-png", "executable", "empty"],
)
async def test_a_rejected_file_keeps_the_current_image(
    db_session: AsyncSession, media: Media, data: bytes, filename: str, content_type: str
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        current = _uploaded(client)
        response = _upload(client, data, filename=filename, content_type=content_type)
        assert_problem(response, 422, "UPLOAD_REJECTED")
        assert response.json()["errors"][0]["loc"] == ["body", "file"]
        assert _public(client) == current
    assert media.stored() == [_key(current)]


async def test_a_too_small_image_is_rejected(db_session: AsyncSession, media: Media) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _upload(client, sample("PNG", size=(399, 800)))
        assert_problem(response, 422, "UPLOAD_REJECTED")
        assert "400 pixels" in response.json()["detail"]
        assert _public(client) is None
    assert media.stored() == []


async def test_malware_and_a_down_scanner_store_nothing(
    db_session: AsyncSession, media: Media
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        current = _uploaded(client)
        assert_problem(
            _upload(client, sample("PNG", size=BIG_ENOUGH) + EICAR), 422, "MALWARE_DETECTED"
        )
        media.scanner.available = False
        assert_problem(_upload(client, sample("PNG", size=BIG_ENOUGH)), 503, "SERVICE_UNAVAILABLE")
        assert _public(client) == current
    assert media.stored() == [_key(current)]


async def test_an_oversized_or_unsized_body_is_refused_before_it_is_read(
    db_session: AsyncSession, media: Media
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        oversized = _upload(client, bytes(MAX_HERO_IMAGE_BYTES + MULTIPART_ALLOWANCE + 1))
        unsized = client.put(
            ADMIN_URL,
            content=iter([b"--x--"]),
            headers={**csrf(client), "content-type": "multipart/form-data; boundary=x"},
        )
    assert_problem(oversized, 422, "UPLOAD_REJECTED")
    assert_problem(unsized, 422, "UPLOAD_REJECTED")
    assert media.stored() == [] and media.scanner.scanned == []


async def test_the_generic_patch_only_clears_it(db_session: AsyncSession, media: Media) -> None:
    """Only the upload names a file; null restores the default brand visual."""
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        current = _uploaded(client)
        for value in (f"home/hero/{'b2' * 16}.png", "https://example.com/x.png"):
            response = client.patch(SETTING_URL, json={"value": value}, headers=csrf(client))
            assert_problem(response, 422, "SETTING_INVALID")
        assert _public(client) == current
        cleared = client.patch(SETTING_URL, json={"value": None}, headers=csrf(client))
        assert cleared.status_code == 200, cleared.text
        assert _public(client) is None


async def test_an_unusable_stored_value_reads_as_the_default(
    db_engine: AsyncEngine, media: Media
) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE settings SET value = '\"https://evil.example/x.png\"'::jsonb "
                "WHERE key = 'homepage_hero_image'"
            )
        )
    with client_for(main_app) as anonymous:
        assert _public(anonymous) is None


async def test_the_admin_boundary_and_csrf_hold(db_session: AsyncSession, media: Media) -> None:
    customer = await create_user(db_session)
    image = sample("PNG", size=BIG_ENOUGH)
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        assert_problem(_upload(admin, image, headers={}), 403, "CSRF_INVALID")
    with client_for(main_app) as anonymous:
        assert_problem(_upload(anonymous, image, headers={}), 401, "AUTH_REQUIRED")
    with client_for(main_app) as client:
        login(client, customer.email)
        assert_problem(_upload(client, image), 404, "NOT_FOUND")
    assert media.stored() == [] and media.scanner.scanned == []
