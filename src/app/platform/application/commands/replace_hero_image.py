"""Replace the homepage hero image (docs/homepage-hero-image.md).

The product-image pipeline (ADR-021), aimed at one setting: size -> scan the raw bytes ->
sanitize (re-encode, metadata stripped) -> store under a fresh key -> point the
`homepage_hero_image` setting at it, audited by `UpdateSetting` in the request's
transaction. The file is written before the setting, so a failed commit leaves only an
unreferenced file, which `reap_orphan_files` removes; the setting never names a missing
file. The replaced file becomes unreferenced the same way and is reaped too - nothing is
deleted while a page that loaded it a moment ago may still ask for it."""

import uuid
from uuid import UUID

from app.integrations.images.ports import ImageRejectedError, ImageSanitizerPort
from app.integrations.scanning.ports import MalwareScannerPort
from app.integrations.storage.ports import StoragePort
from app.platform.application.commands.update_setting import UpdateSetting
from app.platform.application.ports import AuditLog, SettingStore
from app.platform.domain.exceptions import HeroImageMalwareError, HeroImageRejectedError
from app.platform.domain.settings_registry import HERO_IMAGE_PREFIX, HOMEPAGE_HERO_IMAGE_KEY

MAX_HERO_IMAGE_BYTES = 10 * 1024 * 1024  # the product-image limit
# The hero shows the image large (about 600 px square on a desktop, twice that on a
# high-density screen); anything smaller than this would look broken there.
MIN_HERO_IMAGE_SIDE = 400


class ReplaceHeroImage:
    def __init__(
        self,
        settings_repo: SettingStore,
        audit_repo: AuditLog,
        *,
        storage: StoragePort,
        scanner: MalwareScannerPort,
        sanitizer: ImageSanitizerPort,
    ) -> None:
        self._update = UpdateSetting(settings_repo=settings_repo, audit_repo=audit_repo)
        self._storage = storage
        self._scanner = scanner
        self._sanitizer = sanitizer

    async def execute(
        self,
        *,
        data: bytes,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> str:
        """The new storage key, now the setting's value."""
        if not data or len(data) > MAX_HERO_IMAGE_BYTES:
            raise HeroImageRejectedError(f"an image must be 1 byte to {MAX_HERO_IMAGE_BYTES} bytes")
        verdict = await self._scanner.scan(data)
        if not verdict.clean:
            raise HeroImageMalwareError(verdict.signature)
        try:
            clean = await self._sanitizer.sanitize(data)
        except ImageRejectedError as exc:
            raise HeroImageRejectedError(exc.reason) from exc
        if min(clean.width, clean.height) < MIN_HERO_IMAGE_SIDE:
            raise HeroImageRejectedError(
                f"the image must be at least {MIN_HERO_IMAGE_SIDE} pixels on each side"
            )
        key = f"{HERO_IMAGE_PREFIX}{uuid.uuid4().hex}.{clean.extension}"
        await self._storage.put(key, clean.data)
        await self._update.execute(
            key=HOMEPAGE_HERO_IMAGE_KEY,
            value=key,
            actor_user_id=actor_user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
        return key
