from app.integrations.images.pillow import PillowImageSanitizer
from app.integrations.images.ports import ImageSanitizerPort


def get_image_sanitizer() -> ImageSanitizerPort:
    """FastAPI dependency, so the composition root stays in one place."""
    return PillowImageSanitizer()
