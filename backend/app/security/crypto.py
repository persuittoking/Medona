"""Field-level encryption (Fernet) for PII columns, keyed PINFL hash, plus UI masking helpers."""
import hashlib
import hmac
from functools import lru_cache

from cryptography.fernet import Fernet

from app.config import get_settings


def hash_pinfl(pinfl: str) -> str:
    """Keyed HMAC-SHA256 of a JShShIR for exact-match lookup while plain JShShIR stays Fernet-encrypted."""
    s = get_settings()
    secret = (s.pinfl_hash_secret or s.jwt_secret).encode()
    return hmac.new(secret, pinfl.strip().encode(), hashlib.sha256).hexdigest()


def pinfl_secret_fingerprint() -> str:
    """Non-reversible fingerprint of the current PINFL hash key: detects a key change without storing the key."""
    s = get_settings()
    secret = (s.pinfl_hash_secret or s.jwt_secret).encode()
    return hmac.new(secret, b"onaradar-pinfl-key-fingerprint", hashlib.sha256).hexdigest()[:24]


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().fernet_key
    if not key:
        raise RuntimeError("FERNET_KEY is not set (see backend/.env.example)")
    return Fernet(key.encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def mask_pinfl(pinfl: str) -> str:
    """'31234567890112' -> '3***********12'."""
    if len(pinfl) < 4:
        return "*" * len(pinfl)
    return pinfl[0] + "*" * (len(pinfl) - 3) + pinfl[-2:]


def mask_name(full_name: str) -> str:
    """'Dilnoza Karimova' -> 'D. K.'"""
    return " ".join(f"{p[0]}." for p in full_name.split() if p)


def mask_phone(phone: str) -> str:
    return phone[:4] + "*" * max(0, len(phone) - 6) + phone[-2:]
