from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import ALGORITHM, create_access_token, hash_password
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.user import User


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
User.__table__.create(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def seed_user(email: str, role: str = "viewer", active: bool = True) -> User:
    db = TestingSessionLocal()
    user = User(
        email=email,
        password_hash=hash_password("StrongTestPassword123!"),
        role=role,
        is_active=active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.expunge(user)
    db.close()
    return user


def token_for(user: User, **claims: object) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "session_version": user.session_version,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=30),
        "type": "access",
    }
    payload.update(claims)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def clear_users() -> None:
    db = TestingSessionLocal()
    db.execute(delete(User))
    db.commit()
    db.close()


def setup_function() -> None:
    clear_users()


def teardown_function() -> None:
    clear_users()


def test_session_version_mismatch_revokes_existing_token():
    user = seed_user("revoked@example.com")
    token = token_for(user)
    db = TestingSessionLocal()
    db.query(User).filter(User.id == user.id).update(
        {User.session_version: user.session_version + 1}
    )
    db.commit()
    db.close()

    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["detail"] == "Session has been revoked"


def test_password_or_role_change_can_revoke_prior_token():
    user = seed_user("credential-revocation@example.com", role="admin")
    token = token_for(user)
    db = TestingSessionLocal()
    db.query(User).filter(User.id == user.id).update(
        {User.session_version: user.session_version + 1, User.role: "analyst"}
    )
    db.commit()
    db.close()

    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


def test_inactive_user_cannot_use_current_token():
    user = seed_user("inactive@example.com")
    token = token_for(user)
    db = TestingSessionLocal()
    db.query(User).filter(User.id == user.id).update({User.is_active: False})
    db.commit()
    db.close()

    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or inactive user"


def test_token_with_invalid_subject_is_rejected():
    user = seed_user("bad-subject@example.com")
    token = token_for(user, sub="not-an-integer")
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


def test_token_with_negative_session_version_is_rejected():
    user = seed_user("negative-session@example.com")
    token = token_for(user, session_version=-1)
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


def test_token_with_non_access_type_is_rejected():
    user = seed_user("wrong-type@example.com")
    token = token_for(user, type="refresh")
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


def test_token_role_claim_cannot_escalate_authorization():
    user = seed_user("role-escalation@example.com", role="viewer")
    token = token_for(user, role="admin")
    response = client.post(
        "/api/v1/lotteries",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Blocked", "code": "BLOCK", "country": "CO"},
    )
    assert response.status_code == 403


def test_token_cannot_change_session_version_to_current_without_matching_db():
    user = seed_user("session-bound@example.com")
    token = token_for(user, session_version=user.session_version + 99)
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
