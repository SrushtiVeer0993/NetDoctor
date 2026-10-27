import pytest
from pydantic import ValidationError

import bcrypt

from app.core.security import (
    hash_password, password_hash_needs_upgrade, verify_password,
)
from app.core.config import Settings
from app.schemas.auth import UserCreate


def test_registration_accepts_passwords_longer_than_bcrypt_input_limit():
    user = UserCreate(email="valid@example.com", password="a" * 73)
    assert len(user.password.encode("utf-8")) == 73


def test_password_hashing_uses_all_input_bytes_and_rejects_over_policy_size():
    hashed = hash_password("a" * 72 + "first")
    assert verify_password("a" * 72 + "first", hashed)
    assert not verify_password("a" * 72 + "other", hashed)
    assert not password_hash_needs_upgrade(hashed)

    with pytest.raises(ValueError, match="1024 UTF-8 bytes"):
        hash_password("a" * 1025)


def test_legacy_bcrypt_hash_can_be_verified_and_is_marked_for_upgrade():
    legacy_hash = bcrypt.hashpw(b"a" * 72, bcrypt.gensalt()).decode("utf-8")

    assert verify_password("a" * 72 + "legacy suffix", legacy_hash)
    assert password_hash_needs_upgrade(legacy_hash)

    upgraded = hash_password("a" * 72 + "legacy suffix")
    assert verify_password("a" * 72 + "legacy suffix", upgraded)
    assert not verify_password("a" * 72 + "different suffix", upgraded)


def test_registration_rejects_password_above_policy_limit():
    with pytest.raises(ValidationError, match="1024 UTF-8 bytes"):
        UserCreate(email="valid@example.com", password="é" * 513)


def test_production_configuration_rejects_placeholder_signing_secret():
    with pytest.raises(ValidationError, match="Production requires a SECRET_KEY"):
        Settings(ENVIRONMENT="production", SECRET_KEY="replace-with-a-secret")
