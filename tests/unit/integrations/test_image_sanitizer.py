"""SEC-13/SEC-14: accepted by content only, and re-encoded to bare pixels."""

import contextlib
import io
import random

import pytest
from PIL import Image

from app.integrations.images.pillow import MAX_PIXELS, sanitize_bytes, sniff
from app.integrations.images.ports import ImageRejectedError
from app.integrations.scanning.fake import EICAR
from tests.image_samples import SECRET, huge_png, sample

FORMATS = [
    ("JPEG", "jpg", "image/jpeg"),
    ("PNG", "png", "image/png"),
    ("WEBP", "webp", "image/webp"),
]


@pytest.mark.parametrize(("fmt", "extension", "content_type"), FORMATS)
def test_each_accepted_format_keeps_its_family(fmt: str, extension: str, content_type: str) -> None:
    result = sanitize_bytes(sample(fmt))
    assert (result.extension, result.content_type) == (extension, content_type)
    assert (result.width, result.height) == (4, 2)
    with Image.open(io.BytesIO(result.data)) as decoded:
        assert decoded.format == fmt


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_exif_gps_and_text_metadata_are_stripped(fmt: str) -> None:
    upload = sample(fmt)
    assert SECRET.encode() in upload
    result = sanitize_bytes(upload)
    assert SECRET.encode() not in result.data
    assert b"Exif" not in result.data
    with Image.open(io.BytesIO(result.data)) as decoded:
        assert not decoded.getexif()
        assert "exif" not in decoded.info and "icc_profile" not in decoded.info


def test_the_orientation_is_applied_before_the_exif_is_dropped() -> None:
    result = sanitize_bytes(sample("JPEG", size=(4, 2), orientation=6))
    assert (result.width, result.height) == (2, 4)


def test_bytes_appended_after_the_image_do_not_survive() -> None:
    """A polyglot: a valid JPEG with a payload behind its end marker."""
    result = sanitize_bytes(sample("JPEG") + EICAR)
    assert EICAR not in result.data


@pytest.mark.parametrize(
    "data",
    [
        b"plain text pretending to be a photo",
        EICAR,
        b"GIF89a" + b"\x00" * 32,
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        b"\xff\xd8\xff" + b"\x00" * 64,
        sample("PNG")[:40],
        b"",
    ],
    ids=["text", "eicar", "gif", "svg", "jpeg-magic-garbage", "truncated-png", "empty"],
)
def test_anything_but_a_decodable_jpeg_png_or_webp_is_rejected(data: bytes) -> None:
    with pytest.raises(ImageRejectedError):
        sanitize_bytes(data)


def test_the_type_comes_from_magic_bytes_not_a_name() -> None:
    found = sniff(sample("PNG"))
    assert found is not None and found.extension == "png"
    assert sniff(bytes([0x89]) + b"PNX") is None


def test_a_decompression_bomb_is_rejected_before_decoding() -> None:
    with pytest.raises(ImageRejectedError, match="pixels"):
        sanitize_bytes(huge_png(8_000, MAX_PIXELS // 8_000 + 1))


def test_exactly_the_pixel_cap_is_accepted() -> None:
    assert sanitize_bytes(huge_png(8_000, MAX_PIXELS // 8_000)).width == 8_000


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_corrupted_images_are_rejected_never_crash(fmt: str) -> None:
    """Seeded byte flips over images with EXIF orientation; corrupt EXIF once gave a 500."""
    rng = random.Random(1405)
    base = sample(fmt, orientation=6)
    for _ in range(400):
        data = bytearray(base)
        for _ in range(rng.randint(1, 8)):
            data[rng.randrange(len(data))] = rng.randrange(256)
        with contextlib.suppress(ImageRejectedError):
            sanitize_bytes(bytes(data))
