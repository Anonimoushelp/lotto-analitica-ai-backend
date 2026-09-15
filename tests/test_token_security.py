from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security import ALGORITHM, create_access_token, decode_access_token


def test_access_token_contains_required_security_claims():
    token = create_access_token("123", "analyst")
    payload = decode_access_token(token)

    assert payload["sub"] == "123"
    assert payload["role"] == "analyst"
    assert payload["session_version"] == 0
    assert payload["type"] == "access"
    assert payload["iat"] <= datetime.now(UTC).timestamp()
    assert payload["exp"] > datetime.now(UTC).timestamp()


def test_access_token_has_bounded_lifetime():
    token = create_access_token("123", "analyst")
    payload = decode_access_token(token)

    lifetime = payload["exp"] - payload["iat"]
    assert lifetime == 30 * 60


def test_expired_access_token_is_rejected():
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "123",
            "role": "analyst",
            "session_version": 0,
            "iat": now - timedelta(minutes=31),
            "exp": now - timedelta(minutes=1),
            "type": "access",
        },
        settings.secret_key,
        algorithm=ALGORITHM,
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_token_with_wrong_type_is_rejected():
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "123",
            "role": "analyst",
            "session_version": 0,
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "type": "refresh",
        },
        settings.secret_key,
        algorithm=ALGORITHM,
    )

    with pytest.raises(jwt.InvalidTokenError, match="Invalid token type"):
        decode_access_token(token)


def test_token_missing_required_claim_is_rejected():
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "123",
            "role": "analyst",
            "session_version": 0,
            "iat": now,
            "exp": now + timedelta(minutes=30),
        },
        settings.secret_key,
        algorithm=ALGORITHM,
    )

    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_access_token(token)


def test_token_signed_with_different_secret_is_rejected():
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "123",
            "role": "admin",
            "session_version": 0,
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "type": "access",
        },
        "wrong-secret",
        algorithm=ALGORITHM,
    )

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token)


def test_token_using_unapproved_algorithm_is_rejected():
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "123",
            "role": "admin",
            "session_version": 0,
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "type": "access",
        },
        "wrong-secret",
        algorithm="HS384",
    )

    with pytest.raises(jwt.InvalidAlgorithmError):
        decode_access_token(token)
