"""Small real images for the upload tests, each carrying metadata to be stripped."""

import io

from PIL import Image

GPS_IFD = 0x8825
ORIENTATION = 0x0112
SECRET = "secret-gps-camera-owner"


def sample(fmt: str, *, size: tuple[int, int] = (4, 2), orientation: int | None = None) -> bytes:
    """`fmt` is JPEG, PNG or WEBP. Embeds EXIF with GPS and an identifying string."""
    image = Image.new("RGB", size, (200, 30, 30))
    exif = Image.Exif()
    exif[0x013B] = SECRET  # Artist
    exif.get_ifd(GPS_IFD)[2] = (33.0, 51.0, 0.0)  # GPSLatitude
    if orientation is not None:
        exif[ORIENTATION] = orientation
    out = io.BytesIO()
    options: dict[str, object] = {"exif": exif.tobytes()}
    if fmt == "PNG":
        from PIL.PngImagePlugin import PngInfo

        info = PngInfo()
        info.add_text("Comment", SECRET)
        options["pnginfo"] = info
    image.save(out, format=fmt, **options)
    return out.getvalue()


def huge_png(width: int, height: int) -> bytes:
    """A 1-bit image: many pixels, tiny file - a decompression-bomb stand-in."""
    out = io.BytesIO()
    Image.new("1", (width, height)).save(out, format="PNG")
    return out.getvalue()
