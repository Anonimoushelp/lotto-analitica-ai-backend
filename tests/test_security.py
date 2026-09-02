from datetime import UTC, datetime

import jwt

from app.core.config import settings
from app.core.security import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_is_hashed_and_verifies():
    password = "StrongTestPassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("WrongPassword123!", hashed)


def test_access_token_contains_required_claims():
    token = create_access_token("123", "admin")
    payload = decode_access_token(token)

    assert payload["sub"] == "123"
    assert payload["role"] == "admin"
    assert payload["type"] == "access"
    assert datetime.fromtimestamp(payload["exp"], tz=UTC) > datetime.now(UTC)


def test_access_token_rejects_wrong_secret():
    token = create_access_token("123", "admin")

    try:
        jwt.decode(token, "wrong-secret", algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        pass
    else:
        raise AssertionError("Token unexpectedly accepted with wrong secret")

    assert settings.secret_key
