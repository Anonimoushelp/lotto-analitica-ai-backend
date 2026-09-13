from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import ALGORITHM, create_access_token, hash_password, verify_password
from app.main import app

client = TestClient(app)


def test_login_rejects_invalid_credentials_without_user_enumeration():
    for email, password in (("missing@example.com", "StrongTestPassword123!"), ("bad", "x")):
        response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert response.status_code in {401, 422}
        if response.status_code == 401:
            assert response.json()["detail"] == "Invalid credentials"


def test_login_rejects_oversized_password_at_schema_boundary():
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "valid@example.com", "password": "x" * 129},
    )
    assert response.status_code == 422


def test_registration_is_blocked_when_initial_registration_disabled():
    original = settings.allow_initial_registration
    settings.allow_initial_registration = False
    try:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "bootstrap@example.com",
                "password": "StrongTestPassword123!",
                "role": "viewer",
            },
        )
        assert response.status_code == 403
    finally:
        settings.allow_initial_registration = original


def test_access_token_contains_required_security_claims():
    token = create_access_token("123", "viewer", session_version=4)
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    assert payload["sub"] == "123"
    assert payload["role"] == "viewer"
    assert payload["session_version"] == 4
    assert payload["type"] == "access"
    assert isinstance(payload["iat"], int)
    assert isinstance(payload["exp"], int)
    assert payload["exp"] > payload["iat"]


def test_password_hash_is_not_reversible_and_wrong_password_fails():
    password = "StrongTestPassword123!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("WrongPassword123!", hashed)


def test_token_expiration_is_enforced():
    payload = {
        "sub": "123",
        "role": "viewer",
        "session_version": 0,
        "iat": datetime.now(UTC) - timedelta(minutes=31),
        "exp": datetime.now(UTC) - timedelta(seconds=1),
        "type": "access",
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_none_algorithm_token_is_rejected():
    payload = {
        "sub": "123",
        "role": "admin",
        "session_version": 0,
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
        "type": "access",
    }
    token = jwt.encode(payload, key="", algorithm="none")
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_wrong_hmac_algorithm_is_rejected():
    payload = {
        "sub": "123",
        "role": "admin",
        "session_version": 0,
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
        "type": "access",
    }
    token = jwt.encode(payload, settings.secret_key, algorithm="HS384")
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_malformed_claim_types_are_rejected():
    base = {
        "sub": "123",
        "role": "viewer",
        "session_version": 0,
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
        "type": "access",
    }
    for claim, value in (("role", 1), ("session_version", "0"), ("iat", "now"), ("exp", "later")):
        payload = {**base, claim: value}
        token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
