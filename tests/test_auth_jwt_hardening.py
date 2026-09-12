from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.security import ALGORITHM, create_access_token, settings
from app.db.session import get_db
from app.main import app
from app.models.lottery import Lottery
from app.models.user import User
from tests.test_auth import TestingSessionLocal, override_get_db, seed_user


client = TestClient(app)


def _cleanup() -> None:
    db = TestingSessionLocal()
    db.execute(delete(Lottery))
    db.execute(delete(User))
    db.commit()
    db.close()


def setup_function():
    _cleanup()
    app.dependency_overrides[get_db] = override_get_db


def teardown_function():
    _cleanup()
    app.dependency_overrides.pop(get_db, None)


def test_bearer_scheme_is_case_insensitive_and_non_bearer_is_rejected():
    user = seed_user("jwt-scheme@example.com", "admin")
    token = create_access_token(str(user.id), user.role)

    accepted = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"bEaReR {token}"}
    )
    rejected = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Basic {token}"}
    )

    assert accepted.status_code == 200
    assert rejected.status_code == 401
    assert rejected.headers["WWW-Authenticate"] == "Bearer"


def test_token_signed_with_wrong_algorithm_is_rejected():
    user = seed_user("jwt-algorithm@example.com", "admin")
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role,
            "session_version": user.session_version,
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "type": "access",
        },
        settings.secret_key,
        algorithm="HS384",
    )

    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401


def test_token_with_non_integer_subject_is_rejected():
    user = seed_user("jwt-sub@example.com", "admin")
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "1.5",
            "role": "admin",
            "session_version": user.session_version,
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "type": "access",
        },
        settings.secret_key,
        algorithm=ALGORITHM,
    )

    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401


def test_token_with_invalid_access_type_is_rejected():
    user = seed_user("jwt-type@example.com", "admin")
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role,
            "session_version": user.session_version,
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "type": "refresh",
        },
        settings.secret_key,
        algorithm=ALGORITHM,
    )

    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401


def test_token_role_cannot_elevate_a_viewer():
    user = seed_user("jwt-escalation@example.com", "viewer")
    token = create_access_token(str(user.id), "admin")

    response = client.post(
        "/api/v1/lotteries",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Escalation", "code": "ESC", "country": "CO"},
    )

    assert response.status_code == 403


def test_session_version_revokes_existing_token():
    user = seed_user("jwt-revocation@example.com", "viewer")
    token = create_access_token(
        str(user.id), user.role, session_version=user.session_version
    )

    accepted = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert accepted.status_code == 200

    db = TestingSessionLocal()
    persisted = db.get(User, user.id)
    persisted.session_version += 1
    db.commit()
    db.close()

    revoked = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert revoked.status_code == 401
    assert revoked.headers["WWW-Authenticate"] == "Bearer"
    assert revoked.json()["detail"] == "Session has been revoked"


def test_token_with_negative_session_version_is_rejected():
    user = seed_user("jwt-session-negative@example.com", "viewer")
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role,
            "session_version": -1,
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "type": "access",
        },
        settings.secret_key,
        algorithm=ALGORITHM,
    )

    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
