"""Local development serves public media (docs/homepage-hero-image.md, docs/product-images.md).

The API does not serve `/media/*`. In local development the frontend's dev rewrite sends
`/media/*` to `http://localhost:8001` (its MEDIA_PROXY_TARGET). Until the `media` service
existed, that port was served only by a hand-started side process. Without it every
`/media` URL answered 500 through the frontend, and an uploaded homepage hero image never
appeared: the homepage fell back to its default visual. These tests keep the compose stack
serving that directory on that port."""

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]  # PyYAML ships no stubs; no new dependency for one test

from app.core.config import Settings

COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"
MEDIA_PORT = 8001  # the frontend's documented MEDIA_PROXY_TARGET (http://localhost:8001)


def _services() -> dict[str, Any]:
    services: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    return services


def _mount_for(service: dict[str, Any], container_path: str) -> str:
    [mount] = [v for v in service["volumes"] if v.split(":")[1] == container_path]
    return str(mount)


def test_the_stack_serves_public_media_on_the_frontend_media_port() -> None:
    media = _services()["media"]
    assert media["ports"] == [f"127.0.0.1:{MEDIA_PORT}:{MEDIA_PORT}"]
    command = media["command"]
    assert command[:3] == ["python", "-m", "http.server"]
    assert str(MEDIA_PORT) in command
    assert command[command.index("--directory") + 1] == "/data/media_public"
    assert media["restart"] == "unless-stopped"


def test_it_serves_the_same_directory_the_api_writes_uploads_to_read_only() -> None:
    services = _services()
    api_dir = Settings.model_fields["media_public_dir"].default
    assert api_dir == "/data/media_public"
    api_mount = _mount_for(services["api"], api_dir)
    media_mount = _mount_for(services["media"], api_dir)
    assert media_mount == f"{api_mount}:ro"


def test_it_reuses_the_api_image_and_does_not_inherit_the_api_healthcheck() -> None:
    media = _services()["media"]
    assert media["image"] == "bekaa3d-backend-api"
    assert media["pull_policy"] == "never"
    assert media["healthcheck"] == {"disable": True}
    assert "env_file" not in media and "environment" not in media
