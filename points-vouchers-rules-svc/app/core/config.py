from __future__ import annotations
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    database_url: str = Field(..., alias="DATABASE_URL")
    auth_jwks_url: str = Field(..., alias="AUTH_JWKS_URL")
    token_issuer: str = Field("authentication-svc", alias="TOKEN_ISSUER")

    default_checkin_points: int = Field(10, alias="DEFAULT_CHECKIN_POINTS")

    nats_urls: str = Field("nats://127.0.0.1:4222", alias="NATS_URLS")
    nats_subject_checkin: str = Field("checkins.recorded", alias="NATS_SUBJECT_CHECKIN")
    enable_nats_consumer: bool = Field(default=True, alias="ENABLE_NATS_CONSUMER")

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
