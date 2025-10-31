# app/core/jwks.py
from __future__ import annotations
import base64
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from .config import get_settings
settings = get_settings()

def _b64url_uint(i: int) -> str:
    raw = i.to_bytes((i.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

def build_rsa_jwk() -> dict:
    pub = load_pem_public_key(settings.jwt_public_key.encode("utf-8"))
    assert isinstance(pub, RSAPublicKey), "Public key must be RSA"
    numbers = pub.public_numbers()
    return {
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "kid": settings.token_issuer,  # simple, stable kid
        "n": _b64url_uint(numbers.n),
        "e": _b64url_uint(numbers.e),
    }
