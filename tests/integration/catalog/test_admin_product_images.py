"""`/api/v1/admin/products/{id}/images` (VS-014): the upload pipeline, cover and
order rules, soft delete, audit, the admin boundary and CSRF."""

import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.catalog.api.product_images import MULTIPART_ALLOWANCE
from app.catalog.application.commands.product_image_admin import MAX_UPLOAD_BYTES
from app.catalog.domain.product_image import MAX_IMAGES_PER_PRODUCT
from app.catalog.infrastructure.models import ProductImageModel
from app.integrations.scanning.factory import get_malware_scanner
from app.integrations.scanning.fake import EICAR, FakeScanner
from app.integrations.storage.factory import get_public_media_storage
from app.integrations.storage.local import LocalStorage
from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.image_samples import SECRET, sample
from tests.integration.catalog.test_admin_products import (
    PRODUCTS,
    _audit,
    _create,
    _delete,
    _refs,
    _stl,
)
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


class Media:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.storage = LocalStorage(root)
        self.scanner = FakeScanner()

    def files(self) -> list[Path]:
        return sorted(p for p in self.root.rglob("*") if p.is_file())


@pytest.fixture
def media(tmp_path: Path) -> Generator[Media]:
    media = Media(tmp_path / "media")
    main_app.dependency_overrides[get_public_media_storage] = lambda: media.storage
    main_app.dependency_overrides[get_malware_scanner] = lambda: media.scanner
    yield media
    main_app.dependency_overrides.pop(get_public_media_storage, None)
    main_app.dependency_overrides.pop(get_malware_scanner, None)


def _images(product_id: str) -> str:
    return f"{PRODUCTS}/{product_id}/images"


def _upload(
    client: TestClient,
    product_id: str,
    data: bytes,
    *,
    filename: str = "photo.jpg",
    content_type: str = "image/jpeg",
    alt_text: str | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    form = {"alt_text": alt_text} if alt_text is not None else {}
    return client.post(
        _images(product_id),
        files={"file": (filename, data, content_type)},
        data=form,
        headers=csrf(client) if headers is None else headers,
    )


def _uploaded(client: TestClient, product_id: str, fmt: str = "JPEG", **kw: Any) -> dict[str, Any]:
    response = _upload(client, product_id, sample(fmt), **kw)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def _product(client: TestClient, db: AsyncSession) -> dict[str, Any]:
    await mfa_admin(client, db)
    return _create(client, _stl(await _refs(db)))


async def _rows(db: AsyncSession, product_id: str) -> list[ProductImageModel]:
    db.expire_all()
    stmt = select(ProductImageModel).where(ProductImageModel.product_id == uuid.UUID(product_id))
    return list(await db.scalars(stmt))


# --- the upload pipeline (ADR-021) -----------------------------------------


@pytest.mark.parametrize(("fmt", "extension"), [("JPEG", "jpg"), ("PNG", "png"), ("WEBP", "webp")])
async def test_a_stored_file_is_the_reencoded_output_never_the_upload(
    db_session: AsyncSession, media: Media, fmt: str, extension: str
) -> None:
    upload = sample(fmt)
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        image = _uploaded(client, product["id"], fmt)

    [stored] = media.files()
    key = f"products/{stored.name}"
    assert stored.suffix == f".{extension}"
    assert image["url"] == f"/media/{key}"
    assert stored.read_bytes() != upload and SECRET.encode() not in stored.read_bytes()
    assert media.scanner.scanned == [upload]
    assert (image["is_cover"], image["sort_order"]) == (True, 0)
    [row] = await _rows(db_session, product["id"])
    assert row.storage_key == key


@pytest.mark.parametrize(
    ("data", "filename", "content_type"),
    [
        (b"just text", "photo.jpg", "image/jpeg"),
        (b"GIF89a" + b"\x00" * 40, "anim.gif", "image/gif"),
        (b'<svg xmlns="http://www.w3.org/2000/svg"/>', "logo.png", "image/png"),
        (b"\xff\xd8\xff" + b"\x00" * 100, "broken.jpg", "image/jpeg"),
    ],
    ids=["text-as-jpg", "gif", "svg-as-png", "jpeg-magic-garbage"],
)
async def test_the_content_not_the_name_decides_and_rejects(
    db_session: AsyncSession, media: Media, data: bytes, filename: str, content_type: str
) -> None:
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        response = _upload(
            client, product["id"], data, filename=filename, content_type=content_type
        )

    assert_problem(response, 422, "UPLOAD_REJECTED")
    assert media.files() == [] and await _rows(db_session, product["id"]) == []
    assert [r.action for r in await _audit(db_session, product["id"])] == ["product.created"]


async def test_a_real_image_under_a_misleading_name_is_stored_by_its_content(
    db_session: AsyncSession, media: Media
) -> None:
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        response = _upload(
            client, product["id"], sample("PNG"), filename="evil.exe", content_type="text/plain"
        )
    assert response.status_code == 201, response.text
    assert response.json()["url"].endswith(".png")


@pytest.mark.parametrize("payload", ["eicar", "eicar-behind-a-jpeg"])
async def test_malware_is_detected_on_the_raw_upload(
    db_session: AsyncSession, media: Media, payload: str
) -> None:
    """Scanning the re-encoded output would miss the second: re-encoding drops it (ADR-021)."""
    data = EICAR if payload == "eicar" else sample("JPEG") + EICAR
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        response = _upload(client, product["id"], data)

    assert_problem(response, 422, "MALWARE_DETECTED")
    assert media.files() == [] and await _rows(db_session, product["id"]) == []
    assert [r.action for r in await _audit(db_session, product["id"])] == ["product.created"]


async def test_an_unavailable_scanner_refuses_the_upload(
    db_session: AsyncSession, media: Media
) -> None:
    media.scanner.available = False
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        response = _upload(client, product["id"], sample("JPEG"))

    assert_problem(response, 503, "SERVICE_UNAVAILABLE")
    assert media.files() == [] and await _rows(db_session, product["id"]) == []


@pytest.mark.parametrize(
    ("size", "status"), [(0, 422), (MAX_UPLOAD_BYTES, 201), (MAX_UPLOAD_BYTES + 1, 422)]
)
async def test_the_size_limit_holds_at_its_edge(
    db_session: AsyncSession, media: Media, size: int, status: int
) -> None:
    """Padding behind a valid JPEG reaches the exact size; re-encoding then drops it."""
    data = sample("JPEG") if size else b""
    data += b"\x00" * max(0, size - len(data))
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        response = _upload(client, product["id"], data)
    if status == 201:
        assert response.status_code == 201, response.text
    else:
        assert_problem(response, 422, "UPLOAD_REJECTED")
        assert media.files() == []


async def test_an_oversized_or_unsized_body_is_refused_before_it_is_parsed(
    db_session: AsyncSession, media: Media, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Checked from Content-Length after the admin boundary, before Starlette spools anything."""
    customer = await create_user(db_session)
    big = bytes(MAX_UPLOAD_BYTES + MULTIPART_ALLOWANCE + 1)
    with client_for(main_app) as client:
        product = await _product(client, db_session)

        async def never(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("the body was parsed")

        monkeypatch.setattr(Request, "form", never)
        oversized = _upload(client, product["id"], big)
        unsized = client.post(
            _images(product["id"]),
            content=iter([b"--x--"]),
            headers={**csrf(client), "content-type": "multipart/form-data; boundary=x"},
        )
    with client_for(main_app) as anonymous:
        assert_problem(_upload(anonymous, product["id"], big, headers={}), 401, "AUTH_REQUIRED")
    with client_for(main_app) as other:
        login(other, customer.email)
        assert_problem(_upload(other, product["id"], big), 404, "NOT_FOUND")

    assert_problem(oversized, 422, "UPLOAD_REJECTED")
    assert_problem(unsized, 422, "UPLOAD_REJECTED")
    assert media.files() == [] and media.scanner.scanned == []


async def test_the_image_cap_refuses_one_more(db_session: AsyncSession, media: Media) -> None:
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        for _ in range(MAX_IMAGES_PER_PRODUCT):
            _uploaded(client, product["id"])
        response = _upload(client, product["id"], sample("JPEG"))
    assert_problem(response, 422, "UPLOAD_REJECTED")
    assert len(media.files()) == MAX_IMAGES_PER_PRODUCT


@pytest.mark.parametrize("alt_text", ["x" * 301, "bad\x00alt"])
async def test_bad_alt_text_on_upload_is_422_and_stores_nothing(
    db_session: AsyncSession, media: Media, alt_text: str
) -> None:
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        response = _upload(client, product["id"], sample("JPEG"), alt_text=alt_text)
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert media.files() == []


# --- cover, order, alt text, delete ----------------------------------------


async def test_later_uploads_append_and_the_detail_lists_live_images_in_order(
    db_session: AsyncSession, media: Media
) -> None:
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        a, b, c = (_uploaded(client, product["id"]) for _ in range(3))
        assert (
            client.delete(f"{_images(product['id'])}/{b['id']}", headers=csrf(client)).status_code
            == 204
        )
        detail = client.get(f"{PRODUCTS}/{product['id']}").json()

    assert [i["id"] for i in detail["images"]] == [a["id"], c["id"]]
    assert [(i["sort_order"], i["is_cover"]) for i in detail["images"]] == [(0, True), (2, False)]


async def test_list_and_patch_responses_carry_each_products_own_images(
    db_session: AsyncSession, media: Media
) -> None:
    """The list batches images for a page; a mis-keyed grouping would cross products."""
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        other = _create(client, _stl({"category_id": product["category_id"]}))
        a, b = _uploaded(client, product["id"]), _uploaded(client, product["id"])
        c = _uploaded(client, other["id"])
        client.put(
            f"{_images(product['id'])}/order",
            json={"image_ids": [b["id"], a["id"]]},
            headers=csrf(client),
        )
        listed = client.get(PRODUCTS, params={"category_id": product["category_id"]}).json()
        patched = client.patch(
            f"{PRODUCTS}/{product['id']}",
            json={"version": product["version"], "name": "Renamed"},
            headers=csrf(client),
        ).json()

    by_product = {p["id"]: [i["id"] for i in p["images"]] for p in listed["items"]}
    assert by_product == {product["id"]: [b["id"], a["id"]], other["id"]: [c["id"]]}
    assert [i["id"] for i in patched["images"]] == [b["id"], a["id"]]


async def test_setting_the_cover_moves_it(db_session: AsyncSession, media: Media) -> None:
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        a, b = _uploaded(client, product["id"]), _uploaded(client, product["id"])
        response = client.put(f"{_images(product['id'])}/{b['id']}/cover", headers=csrf(client))
        again = client.put(f"{_images(product['id'])}/{b['id']}/cover", headers=csrf(client))
        images = client.get(f"{PRODUCTS}/{product['id']}").json()["images"]

    assert response.status_code == 200 and response.json()["is_cover"] is True
    assert again.status_code == 200
    assert {i["id"]: i["is_cover"] for i in images} == {a["id"]: False, b["id"]: True}


async def test_reorder_sets_the_exact_order(db_session: AsyncSession, media: Media) -> None:
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        ids = [_uploaded(client, product["id"])["id"] for _ in range(3)]
        response = client.put(
            f"{_images(product['id'])}/order",
            json={"image_ids": [ids[2], ids[0], ids[1]]},
            headers=csrf(client),
        )
    assert response.status_code == 200, response.text
    assert [(i["id"], i["sort_order"]) for i in response.json()["items"]] == [
        (ids[2], 0),
        (ids[0], 1),
        (ids[1], 2),
    ]


@pytest.mark.parametrize("case", ["missing", "extra", "duplicate", "deleted", "foreign"])
async def test_reorder_must_name_exactly_the_live_images(
    db_session: AsyncSession, media: Media, case: str
) -> None:
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        other = _create(client, _stl(await _refs(db_session)))
        ids = [_uploaded(client, product["id"])["id"] for _ in range(3)]
        gone = _uploaded(client, product["id"])["id"]
        assert (
            client.delete(f"{_images(product['id'])}/{gone}", headers=csrf(client)).status_code
            == 204
        )
        foreign = _uploaded(client, other["id"])["id"]
        bad = {
            "missing": ids[:2],
            "extra": [*ids, str(uuid.uuid4())],
            "duplicate": [ids[0], *ids],
            "deleted": [*ids, gone],
            "foreign": [*ids[:2], foreign],
        }[case]
        response = client.put(
            f"{_images(product['id'])}/order", json={"image_ids": bad}, headers=csrf(client)
        )
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_alt_text_updates_clears_and_is_validated(
    db_session: AsyncSession, media: Media
) -> None:
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        image = _uploaded(client, product["id"], alt_text="  A red lamp  ")
        path = f"{_images(product['id'])}/{image['id']}"
        renamed = client.patch(path, json={"alt_text": "Blue lamp"}, headers=csrf(client))
        cleared = client.patch(path, json={"alt_text": "   "}, headers=csrf(client))
        too_long = client.patch(path, json={"alt_text": "x" * 301}, headers=csrf(client))
        missing = client.patch(path, json={}, headers=csrf(client))

    assert image["alt_text"] == "A red lamp"
    assert renamed.json()["alt_text"] == "Blue lamp"
    assert cleared.json()["alt_text"] is None
    assert_problem(too_long, 422, "VALIDATION_ERROR")
    assert_problem(missing, 422, "VALIDATION_ERROR")


async def test_the_cover_cannot_be_deleted_while_others_remain(
    db_session: AsyncSession, media: Media
) -> None:
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        cover, other = _uploaded(client, product["id"]), _uploaded(client, product["id"])
        path = _images(product["id"])
        blocked = client.delete(f"{path}/{cover['id']}", headers=csrf(client))
        other_gone = client.delete(f"{path}/{other['id']}", headers=csrf(client))
        last_gone = client.delete(f"{path}/{cover['id']}", headers=csrf(client))

    assert_problem(blocked, 409, "INVALID_STATE_TRANSITION")
    assert (other_gone.status_code, last_gone.status_code) == (204, 204)
    rows = await _rows(db_session, product["id"])
    assert all(r.deleted_at is not None and not r.is_cover for r in rows)
    assert len(media.files()) == 2, "soft delete keeps the files (BR-033)"


@pytest.mark.parametrize("operation", ["patch", "cover", "delete"])
async def test_an_image_of_another_product_is_404(
    db_session: AsyncSession, media: Media, operation: str
) -> None:
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        other = _create(client, _stl(await _refs(db_session)))
        foreign = _uploaded(client, other["id"])
        path = f"{_images(product['id'])}/{foreign['id']}"
        response = {
            "patch": lambda: client.patch(path, json={"alt_text": "x"}, headers=csrf(client)),
            "cover": lambda: client.put(f"{path}/cover", headers=csrf(client)),
            "delete": lambda: client.delete(path, headers=csrf(client)),
        }[operation]()
    assert_problem(response, 404, "NOT_FOUND")


def _operations(product_id: str, image_id: str) -> dict[str, tuple[str, str, Any]]:
    base = _images(product_id)
    return {
        "upload": ("POST", base, None),
        "patch": ("PATCH", f"{base}/{image_id}", {"alt_text": "x"}),
        "cover": ("PUT", f"{base}/{image_id}/cover", None),
        "order": ("PUT", f"{base}/order", {"image_ids": [image_id]}),
        "delete": ("DELETE", f"{base}/{image_id}", None),
    }


def _send(client: TestClient, op: tuple[str, str, Any], headers: dict[str, str]) -> Any:
    method, path, body = op
    if method == "POST":
        return client.post(
            path, files={"file": ("a.jpg", sample("JPEG"), "image/jpeg")}, headers=headers
        )
    return client.request(method, path, json=body, headers=headers)


@pytest.mark.parametrize("name", ["upload", "patch", "cover", "order", "delete"])
async def test_a_deleted_product_takes_no_image_changes(
    db_session: AsyncSession, media: Media, name: str
) -> None:
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        image = _uploaded(client, product["id"])
        assert _delete(client, product["id"], 1).status_code == 204
        response = _send(client, _operations(product["id"], image["id"])[name], csrf(client))
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    assert len(media.files()) == 1


async def test_non_admins_get_the_boundary_answers_and_csrf_is_required(
    db_session: AsyncSession, media: Media
) -> None:
    customer = await create_user(db_session)
    with client_for(main_app) as admin:
        product = await _product(admin, db_session)
        image = _uploaded(admin, product["id"])
        operations = _operations(product["id"], image["id"])
        for op in operations.values():
            assert_problem(_send(admin, op, {}), 403, "CSRF_INVALID")
    for op in operations.values():
        with client_for(main_app) as anonymous:
            assert_problem(_send(anonymous, op, {}), 401, "AUTH_REQUIRED")
        with client_for(main_app) as client:
            login(client, customer.email)
            assert_problem(_send(client, op, csrf(client)), 404, "NOT_FOUND")
    assert len(media.files()) == 1


async def test_an_unknown_product_is_404_and_stores_nothing(
    db_session: AsyncSession, media: Media
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _upload(client, str(uuid.uuid4()), sample("JPEG"))
    assert_problem(response, 404, "NOT_FOUND")
    assert media.files() == [] and media.scanner.scanned == []


# --- audit and failure -----------------------------------------------------


async def test_every_image_write_is_audited(db_session: AsyncSession, media: Media) -> None:
    with client_for(main_app) as client:
        product = await _product(client, db_session)
        a, b = _uploaded(client, product["id"]), _uploaded(client, product["id"])
        base = _images(product["id"])
        client.patch(f"{base}/{b['id']}", json={"alt_text": "Side"}, headers=csrf(client))
        client.put(f"{base}/{b['id']}/cover", headers=csrf(client))
        client.put(f"{base}/order", json={"image_ids": [b["id"], a["id"]]}, headers=csrf(client))
        assert client.delete(f"{base}/{a['id']}", headers=csrf(client)).status_code == 204

    on_b = [r.action for r in await _audit(db_session, b["id"])]
    on_a = [r.action for r in await _audit(db_session, a["id"])]
    on_product = [r.action for r in await _audit(db_session, product["id"])]
    assert on_b == ["product_image.uploaded", "product_image.updated"]
    assert on_a == ["product_image.uploaded", "product_image.deleted"]
    assert on_product == ["product.created", "product_image.cover_set", "product_image.reordered"]


class _BrokenStorage(LocalStorage):
    async def put(self, key: str, data: bytes) -> None:
        raise OSError("disk full")


async def test_a_storage_failure_leaves_no_row(db_session: AsyncSession, media: Media) -> None:
    """FR-04: a failed upload never leaves a product pointing at a missing image."""
    main_app.dependency_overrides[get_public_media_storage] = lambda: _BrokenStorage(media.root)
    with client_for(main_app, raise_server_exceptions=False) as client:
        product = await _product(client, db_session)
        response = _upload(client, product["id"], sample("JPEG"))
    assert_problem(response, 500, "INTERNAL_ERROR")
    assert await _rows(db_session, product["id"]) == []
    assert [r.action for r in await _audit(db_session, product["id"])] == ["product.created"]
