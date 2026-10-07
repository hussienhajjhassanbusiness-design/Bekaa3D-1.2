from app.core.config import Settings, get_settings
from app.integrations.storage.local import LocalStorage
from app.integrations.storage.ports import StoragePort


def public_media_storage(settings: Settings) -> StoragePort:
    """Public product media; nginx serves this directory from VS-020."""
    return LocalStorage(settings.media_public_dir)


def get_public_media_storage() -> StoragePort:
    """FastAPI dependency; tests override it with a temporary directory."""
    return public_media_storage(get_settings())
