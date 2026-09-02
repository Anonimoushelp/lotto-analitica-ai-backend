from datetime import UTC, datetime, timedelta

import jwt
import pytest

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


def _token_with_payload(**overrides: object) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": "123",
        "role": "admin",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "type": "access",
    }
    payload.update(overrides)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def test_access_token_rejects_expired_token():
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "123",
            "role": "admin",
            "iat": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
            "type": "access",
        },
        settings.secret_key,
        algorithm=ALGORITHM,
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_access_token_rejects_missing_required_claims():
    required_claims = ("sub", "role", "iat", "exp", "type")

    for claim in required_claims:
        token = _token_with_payload()
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        payload.pop(claim)
        tampered_token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)

        with pytest.raises(jwt.MissingRequiredClaimError):
            decode_access_token(tampered_token)


def test_access_token_rejects_wrong_algorithm():
    token = _token_with_payload()
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    wrong_algorithm_token = jwt.encode(payload, settings.secret_key, algorithm="HS384")

    with pytest.raises(jwt.InvalidAlgorithmError):
        decode_access_token(wrong_algorithm_token)


def test_access_token_rejects_wrong_token_type():
    token = _token_with_payload(type="refresh")

    with pytest.raises(jwt.InvalidTokenError):
        payload = decode_access_token(token)
        assert payload["type"] == "access"


def test_access_token_rejects_tampered_signature():
    token = create_access_token("123", "admin")
    header, payload, signature = token.split(".")
    tampered_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    tampered_token = ".".join((header, payload, tampered_signature))

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(tampered_token)
