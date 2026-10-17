from app.core.config import Settings, get_settings
from app.integrations.storage.local import LocalStorage
from app.integrations.storage.ports import StoragePort


def public_media_storage(settings: Settings) -> StoragePort:
    """Public product media; nginx serves this directory from VS-020."""
    return LocalStorage(settings.media_public_dir)


def get_public_media_storage() -> StoragePort:
    """FastAPI dependency; tests override it with a temporary directory."""
    return public_media_storage(get_settings())


def private_upload_storage(settings: Settings) -> StoragePort:
    """Bring Your Idea attachments: never under the web root (SEC-16, BR-111)."""
    return LocalStorage(settings.uploads_private_dir)


def get_private_upload_storage() -> StoragePort:
    """FastAPI dependency; tests override it with a temporary directory."""
    return private_upload_storage(get_settings())
