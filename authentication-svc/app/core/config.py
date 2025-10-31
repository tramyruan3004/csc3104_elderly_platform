# app/core/config.py
from __future__ import annotations
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import cached_property
from pathlib import Path
from typing import Optional
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


class Settings(BaseSettings):
    # DB
    database_url: str

    # Tokens
    access_token_exp_minutes: int = 15
    refresh_token_exp_minutes: int = 60 * 24 * 7  # 7 days
    token_issuer: str = "authentication-svc"

    # JWT (either supply paths OR inline PEM strings; if neither is supplied, we auto-generate)
    jwt_private_key_path: Optional[str] = Field(default=None)
    jwt_public_key_path: Optional[str] = Field(default=None)
    jwt_private_key_inline: Optional[str] = Field(default=None, alias="JWT_PRIVATE_KEY")
    jwt_public_key_inline: Optional[str] = Field(default=None, alias="JWT_PUBLIC_KEY")

    service_client_id: str | None = Field(default=None, alias="SERVICE_CLIENT_ID")
    service_client_secret: str | None = Field(default=None, alias="SERVICE_CLIENT_SECRET")
    
    class Config:
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False

    # --- Load or generate keys ---
    @cached_property
    def jwt_private_key(self) -> str:
        pem = self._load_pem_from_any(source_path=self.jwt_private_key_path,
                                      inline=self.jwt_private_key_inline)
        if pem:
            return pem
        # generate ephemeral pair
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        return private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

    @cached_property
    def jwt_public_key(self) -> str:
        # try file or inline first
        pem = self._load_pem_from_any(source_path=self.jwt_public_key_path,
                                      inline=self.jwt_public_key_inline)
        if pem:
            return pem
        # otherwise derive from the private key we generated/loaded
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        private_key = load_pem_private_key(self.jwt_private_key.encode("utf-8"), password=None)
        public_key = private_key.public_key()
        return public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

    @staticmethod
    def _load_pem_from_any(*, source_path: Optional[str], inline: Optional[str]) -> Optional[str]:
        if inline and "BEGIN" in inline:
            # Already a PEM block
            return inline
        if source_path:
            p = Path(source_path)
            if p.exists():
                return p.read_text(encoding="utf-8")
        return None


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
