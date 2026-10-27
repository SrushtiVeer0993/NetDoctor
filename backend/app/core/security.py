"""
Password hashing and JWT issuing/verification.
Passwords are never stored or logged in plaintext.

Note: this hashes with the `bcrypt` library directly rather than via
passlib. passlib (last released 2020) has a known incompatibility with
bcrypt>=4.1 (its self-test raises "password cannot be longer than 72
bytes" on import) — calling bcrypt directly avoids that trap entirely.
"""
from datetime import datetime, timedelta, timezone
import hashlib

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

MAX_PASSWORD_BYTES = 1024
_BCRYPT_SHA256_PREFIX = "bcrypt-sha256$"


def _bcrypt_input(password: str) -> bytes:
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be no more than {MAX_PASSWORD_BYTES} UTF-8 bytes")
    return hashlib.sha256(raw).hexdigest().encode("ascii")


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(_bcrypt_input(password), bcrypt.gensalt()).decode("utf-8")
    return _BCRYPT_SHA256_PREFIX + hashed


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        if hashed_password.startswith(_BCRYPT_SHA256_PREFIX):
            return bcrypt.checkpw(
                _bcrypt_input(plain_password),
                hashed_password[len(_BCRYPT_SHA256_PREFIX):].encode("utf-8"),
            )

        # Compatibility for older bcrypt hashes, whose input was truncated
        # to 72 bytes. The login route upgrades a successful legacy hash.
        raw = plain_password.encode("utf-8")
        if len(raw) > MAX_PASSWORD_BYTES:
            return False
        return bcrypt.checkpw(raw[:72], hashed_password.encode("utf-8"))
    except ValueError:
        return False


def password_hash_needs_upgrade(hashed_password: str) -> bool:
    return not hashed_password.startswith(_BCRYPT_SHA256_PREFIX)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None
