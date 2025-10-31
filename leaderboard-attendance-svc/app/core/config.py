from __future__ import annotations
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # DB
    database_url: str = Field(..., alias="DATABASE_URL")

    # Auth (for organiser/attendee endpoints)
    auth_jwks_url: str = Field(..., alias="AUTH_JWKS_URL")
    token_issuer: str = Field("authentication-svc", alias="TOKEN_ISSUER")

    # NATS
    nats_urls: str = Field("nats://127.0.0.1:4222", alias="NATS_URLS")
    subject_checkin: str = Field("checkins.recorded", alias="NATS_SUBJECT_CHECKIN")
    enable_nats_consumer: bool = Field(default=True, alias="ENABLE_NATS_CONSUMER")

    # Leaderboard logic
    # scoring can be "checkins" (count) for now; you can extend to "points" later
    scoring_mode: str = Field("checkins", alias="SCORING_MODE")

    # cron-like rebuild cadence for ranks (seconds)
    ranks_rebuild_interval_sec: int = Field(60, alias="RANKS_REBUILD_INTERVAL_SEC")

    class Config:
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False

_settings: Settings | None = None
def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
