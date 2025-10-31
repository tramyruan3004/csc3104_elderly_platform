from __future__ import annotations
from pydantic_settings import BaseSettings
from pydantic import Field
import secrets

class Settings(BaseSettings):
    database_url: str = Field(..., alias="DATABASE_URL")

    auth_jwks_url: str = Field(..., alias="AUTH_JWKS_URL")
    token_issuer: str = Field("authentication-svc", alias="TOKEN_ISSUER")

    trails_base_url: str = Field("http://localhost:8002", alias="TRAILS_BASE_URL")
    points_base_url: str = Field("http://localhost:8003", alias="POINTS_BASE_URL")

    qr_secret: str | None = Field(default=None, alias="QR_SECRET")
    qr_ttl_seconds: int = Field(default=120, alias="QR_TTL_SECONDS")

    # Redis
    redis_url: str = Field("redis://127.0.0.1:6379/0", alias="REDIS_URL")
    rl_enabled: bool = Field(default=True, alias="RL_ENABLED")
    rl_window_seconds: int = Field(default=60, alias="RL_WINDOW_SECONDS")
    rl_max_reqs: int = Field(default=60, alias="RL_MAX_REQS")

    # NATS
    nats_urls: str = Field("nats://127.0.0.1:4222", alias="NATS_URLS")
    nats_subject_checkin: str = Field("checkins.recorded", alias="NATS_SUBJECT_CHECKIN")
    use_nats_for_points: bool = Field(default=True, alias="USE_NATS_FOR_POINTS")

    class Config:
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False

    @property
    def qr_secret_effective(self) -> str:
        return self.qr_secret or secrets.token_urlsafe(48)

_settings: Settings | None = None
def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
