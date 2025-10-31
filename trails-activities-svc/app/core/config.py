from __future__ import annotations
from pydantic_settings import BaseSettings
from pydantic import Field
import secrets

class Settings(BaseSettings):
    database_url: str = Field(..., alias="DATABASE_URL")
    auth_jwks_url: str = Field(..., alias="AUTH_JWKS_URL")
    token_issuer: str = Field("authentication-svc", alias="TOKEN_ISSUER")

    # Invitations
    invite_secret: str | None = Field(default=None, alias="INVITE_SECRET")
    invite_ttl_hours: int = Field(default=168, alias="INVITE_TTL_HOURS")
    invite_base_url: str = Field(default="http://localhost:8002/invites", alias="INVITE_BASE_URL")

    class Config:
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False

    # ephemeral fallback if no INVITE_SECRET provided
    @property
    def invite_secret_effective(self) -> str:
        return self.invite_secret or secrets.token_urlsafe(48)

_settings: Settings | None = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
