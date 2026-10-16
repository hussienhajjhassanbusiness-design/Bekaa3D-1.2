from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    debug: bool = False
    base_url: str = "http://localhost:8000"
    # Where email links point (BUG-09): the customer-facing frontend, not the
    # API. Tokens travel in the URL fragment, which browsers never send to a
    # server - see docs/notification-contract.md "Links in emails".
    frontend_base_url: str = "http://localhost:3000"
    app_version: str = "0.1.0"
    git_commit_sha: str = "unknown"

    database_url: str
    redis_url: str

    jwt_signing_key: str
    csrf_secret: str
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    # The IP-hash pepper (ADR-028); the env name predates the rotating DB salt.
    # Read only by `install_ip_hash_key`; a change needs a restart (lru_cache).
    ip_hash_salt: SecretStr
    # Encrypts the stored TOTP secret (database-design.md 5.6 requires
    # `secret_ciphertext`). Distinct from jwt_signing_key and csrf_secret on
    # purpose: one key, one job, so rotating or leaking one does not widen
    # into the others.
    mfa_secret_key: str
    # Shown by the authenticator app beside the account name.
    mfa_issuer: str = "Bekaa3D"

    storage_root: str = "/data"
    stl_private_dir: str = "/data/stl_private"
    uploads_private_dir: str = "/data/uploads_private"
    media_public_dir: str = "/data/media_public"
    # Public URL prefix the media directory is served under (nginx, VS-020).
    media_public_url: str = "/media"

    scanner: str = "clamav"
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    clamav_timeout_seconds: float = 30.0
    xaccel_prefix: str = "/protected"

    payment_provider: str = "mock"
    whish_base_url: str = ""
    whish_channel: str = ""
    whish_secret: str = ""
    whish_webhook_ips: str = ""
    whish_verify_signature: bool = False

    email_provider: str = "console"
    email_provider_key: str = ""
    email_from: str = "no-reply@example.com"

    captcha_provider: str = "turnstile"
    turnstile_secret: str = ""
    turnstile_timeout_seconds: float = 5.0

    sentry_dsn: str = ""
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
