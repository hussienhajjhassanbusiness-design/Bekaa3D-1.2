import asyncio
import io
import warnings
from dataclasses import dataclass

from PIL import Image, ImageOps

from app.integrations.images.ports import ImageRejectedError, ImageSanitizerPort, SanitizedImage

MAX_PIXELS = 40_000_000


@dataclass(frozen=True)
class _Format:
    pillow: str
    extension: str
    content_type: str
    save_options: dict[str, object]


_JPEG = _Format("JPEG", "jpg", "image/jpeg", {"quality": 90, "optimize": True})
_PNG = _Format("PNG", "png", "image/png", {"optimize": True})
_WEBP = _Format("WEBP", "webp", "image/webp", {"quality": 90, "method": 4})


def sniff(data: bytes) -> _Format | None:
    """Magic bytes only; the format family is kept on re-encode (owner decision)."""
    if data.startswith(b"\xff\xd8\xff"):
        return _JPEG
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return _PNG
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _WEBP
    return None


def _pixels_only(image: Image.Image, fmt: _Format) -> Image.Image:
    """Copy the pixels into a new image, so no metadata from the upload survives."""
    image = ImageOps.exif_transpose(image)
    if image.mode == "P" or "transparency" in image.info:
        image = image.convert("RGBA")
    if fmt is _JPEG and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    if fmt is _WEBP and image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.mode else "RGB")
    return Image.frombytes(image.mode, image.size, image.tobytes())


def sanitize_bytes(data: bytes) -> SanitizedImage:
    fmt = sniff(data)
    if fmt is None:
        raise ImageRejectedError("not a JPEG, PNG or WebP image")
    out = io.BytesIO()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=[fmt.pillow]) as source:
                width, height = source.size
                if width * height > MAX_PIXELS:
                    raise ImageRejectedError(f"image exceeds {MAX_PIXELS} pixels")
                source.load()
                clean = _pixels_only(source, fmt)
            clean.save(out, format=fmt.pillow, **fmt.save_options)
    except ImageRejectedError:
        raise
    except Exception as exc:
        # Malformed input fails in many places (corrupt EXIF raises struct.error, TypeError):
        # every one is the upload's fault, never a 500 (VS-014 review).
        raise ImageRejectedError("image could not be decoded") from exc
    return SanitizedImage(out.getvalue(), fmt.extension, fmt.content_type, *clean.size)


class PillowImageSanitizer(ImageSanitizerPort):
    async def sanitize(self, data: bytes) -> SanitizedImage:
        return await asyncio.to_thread(sanitize_bytes, data)
